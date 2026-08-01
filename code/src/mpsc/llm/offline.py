"""Provider-neutral preparation and read-only verification for LLM evidence."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

DEFAULT_PROMPT_CONFIG = Path("code/configs/llm/mutable_parameter_prompt.yaml")
DEFAULT_SUBJECT_CONFIG = Path("code/configs/llm/control_run_subjects.yaml")
DEFAULT_REVIEW_CONFIG = Path("code/configs/llm/reviewer_protocol.yaml")

REQUIRED_BUNDLE_FILES = (
    "request.json",
    "response.json",
    "parsed_candidates.json",
    "ground_truth.json",
    "review.json",
    "evaluation.json",
    "timing.json",
)
PROTECTED_REDACTION_FILES = {
    "parsed_candidates.json",
    "ground_truth.json",
    "review.json",
    "evaluation.json",
    "timing.json",
}
_CANDIDATE_ID = re.compile(r"C[0-9]{3,}")
_GROUND_TRUTH_ID = re.compile(r"GT[0-9]{3,}")
_ATTEMPT_ID = re.compile(r"A[0-9]{3,}")
_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_SECRET_VALUE = re.compile(
    r"(?i)(?:bearer\s+[A-Za-z0-9._~+/=-]{12,}|"
    r"\bsk-[A-Za-z0-9_-]{12,}|"
    r"\b(?:api[_ -]?key|access[_ -]?token|cookie)\s*[:=]\s*\S+)"
)
_WINDOWS_ABSOLUTE = re.compile(r"(?i)(?:^|[\s\"'])(?:[A-Z]:[\\/]|\\\\[^\\\s]+\\)")
_UNIX_HOME_ABSOLUTE = re.compile(
    r"(?:^|[\s\"'])(?:/(?:home|Users|root|private|tmp)/[^\s\"']+)"
)
_SENSITIVE_KEY = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|authorization|cookie|"
    r"account[_-]?id|email)"
)


class LLMProtocolError(ValueError):
    """Raised when a recorded run is incomplete or internally inconsistent."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _text_sha256(data: bytes) -> str:
    """Hash UTF-8 protocol text with platform line endings normalized to LF."""

    text = data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return _sha256(text.encode())


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return _sha256(payload)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise LLMProtocolError(f"required recorded artifact is missing: {path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LLMProtocolError(f"{path.name} is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise LLMProtocolError(f"{path.name} must contain a JSON object")
    return value


def _require_fields(value: dict[str, Any], fields: tuple[str, ...], label: str) -> None:
    missing = [field for field in fields if field not in value]
    if missing:
        raise LLMProtocolError(f"{label} is missing fields: {', '.join(missing)}")


def _require_nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LLMProtocolError(f"{label} must be a non-empty string")
    return value


def _require_number(
    value: Any,
    label: str,
    *,
    minimum: float,
    maximum: float,
    minimum_inclusive: bool = True,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LLMProtocolError(f"{label} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise LLMProtocolError(f"{label} must be a finite number")
    below = number < minimum if minimum_inclusive else number <= minimum
    if below or number > maximum:
        lower = "[" if minimum_inclusive else "("
        raise LLMProtocolError(f"{label} must be in {lower}{minimum}, {maximum}]")
    return number


def _require_iso_date(value: Any, label: str) -> None:
    try:
        date.fromisoformat(_require_nonempty(value, label))
    except ValueError as error:
        raise LLMProtocolError(f"{label} must use ISO YYYY-MM-DD format") from error


def _require_iso_datetime(value: Any, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(_require_nonempty(value, label))
    except ValueError as error:
        raise LLMProtocolError(f"{label} must be an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise LLMProtocolError(f"{label} must include a timezone")
    return parsed


def _walk_json(value: Any, path: str = "$") -> list[tuple[str, str, str | None]]:
    rows: list[tuple[str, str, str | None]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            if isinstance(item, str):
                rows.append((child, item, key))
            else:
                rows.extend(_walk_json(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            child = f"{path}[{index}]"
            if isinstance(item, str):
                rows.append((child, item, None))
            else:
                rows.extend(_walk_json(item, child))
    return rows


def _check_sensitive_content(filename: str, value: dict[str, Any]) -> None:
    def check_sensitive_keys(item: Any, path: str = "$") -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                child_path = f"{path}.{key}"
                if _SENSITIVE_KEY.fullmatch(key) and child is not None and child != "":
                    raise LLMProtocolError(
                        f"{filename} contains prohibited sensitive field {child_path}"
                    )
                check_sensitive_keys(child, child_path)
        elif isinstance(item, list):
            for index, child in enumerate(item):
                check_sensitive_keys(child, f"{path}[{index}]")

    check_sensitive_keys(value)
    for path, text, _ in _walk_json(value):
        if _EMAIL.search(text):
            raise LLMProtocolError(f"{filename} contains an email address at {path}")
        if _SECRET_VALUE.search(text):
            raise LLMProtocolError(
                f"{filename} contains an apparent credential at {path}"
            )
        if _WINDOWS_ABSOLUTE.search(text) or _UNIX_HOME_ABSOLUTE.search(text):
            raise LLMProtocolError(
                f"{filename} contains an absolute local path at {path}"
            )


def _logical_source_path(source_path: Path) -> str:
    """Return a portable locator without leaking a local absolute path."""

    if not source_path.is_absolute():
        return PurePosixPath(source_path).as_posix()
    try:
        return source_path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return source_path.name


def _load_prompt(prompt_config: Path) -> tuple[dict[str, Any], bytes]:
    if not prompt_config.is_file():
        raise LLMProtocolError(f"prompt config does not exist: {prompt_config}")
    config_bytes = prompt_config.read_bytes()
    config = yaml.safe_load(config_bytes)
    if not isinstance(config, dict):
        raise LLMProtocolError("prompt config must contain a mapping")
    stages = config.get("stages", [])
    if not isinstance(stages, list) or len(stages) != 3:
        raise LLMProtocolError("prompt protocol must contain exactly three stages")
    return config, config_bytes


def _prepared_run_id(
    contract_id: str,
    request_date: str,
    source_bytes: bytes,
    prompt_bytes: bytes,
) -> str:
    return (
        f"llm-{contract_id}-{request_date}-"
        f"{_text_sha256(source_bytes)[:12]}-{_text_sha256(prompt_bytes)[:12]}"
    )


def prepare_offline_run(
    contract_source: str | Path,
    output_dir: str | Path,
    *,
    contract_id: str,
    model_snapshot: str,
    provider: str,
    request_date: str,
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
    seed: int | None = None,
    seed_supported: bool = False,
    prompt_config: str | Path = DEFAULT_PROMPT_CONFIG,
) -> dict[str, Any]:
    """Create one deterministic, explicitly incomplete request preparation."""

    source_path = Path(contract_source)
    config_path = Path(prompt_config)
    if not source_path.is_file():
        raise LLMProtocolError(f"contract source does not exist: {source_path}")
    provider = _require_nonempty(provider, "provider")
    model_snapshot = _require_nonempty(model_snapshot, "model_snapshot")
    contract_id = _require_nonempty(contract_id, "contract_id")
    _require_iso_date(request_date, "request_date")
    if provider.lower() in {"recorded", "provider", "unknown", "todo", "placeholder"}:
        raise LLMProtocolError("provider must identify the actual intended provider")
    if model_snapshot.lower() in {"model", "unknown", "todo", "placeholder"}:
        raise LLMProtocolError("model_snapshot must be an exact intended model ID")
    if not isinstance(seed_supported, bool):
        raise LLMProtocolError("seed_supported must be boolean")
    if seed_supported and seed is None:
        raise LLMProtocolError("seed is required when seed_supported is true")
    if seed is not None and (
        not seed_supported or isinstance(seed, bool) or not isinstance(seed, int)
    ):
        raise LLMProtocolError(
            "seed must be an integer supported by the selected provider/model"
        )
    if temperature is not None:
        _require_number(
            temperature,
            "temperature",
            minimum=0,
            maximum=2,
        )
    if top_p is not None:
        _require_number(
            top_p,
            "top_p",
            minimum=0,
            maximum=1,
            minimum_inclusive=False,
        )
    if max_tokens is not None and (
        isinstance(max_tokens, bool)
        or not isinstance(max_tokens, int)
        or max_tokens <= 0
    ):
        raise LLMProtocolError("max_tokens must be a positive integer")

    source_bytes = source_path.read_bytes()
    source_text = source_bytes.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    config, config_bytes = _load_prompt(config_path)
    source_hash = _text_sha256(source_bytes)
    prompt_hash = _text_sha256(config_bytes)
    run_id = _prepared_run_id(
        contract_id,
        request_date,
        source_bytes,
        config_bytes,
    )
    delimiter = config["source_delimiter"]
    rendered_stages = [
        {
            "id": stage["id"],
            "role": "user",
            "template": stage["instruction"],
            "rendered_content": (
                f"{stage['instruction']}\n\n{delimiter}\n{source_text}"
            ),
        }
        for stage in config["stages"]
    ]
    messages = [
        {
            "order": 0,
            "role": "system",
            "content": config["system_message"],
        }
    ]
    messages.extend(
        {
            "order": index,
            "role": stage["role"],
            "content": stage["rendered_content"],
            "stage_id": stage["id"],
        }
        for index, stage in enumerate(rendered_stages, start=1)
    )
    request = {
        "schema_version": 2,
        "run_id": run_id,
        "evidence_class": "control",
        "status": "prepared_not_executed",
        "request_date": request_date,
        "contract": {
            "id": contract_id,
            "source_path": _logical_source_path(source_path),
            "source_sha256": source_hash,
            "source_text": source_text,
        },
        "prompt": {
            "template_id": config["template_id"],
            "template_sha256": prompt_hash,
            "system_template": config["system_message"],
            "stages": rendered_stages,
            "messages_in_provider_order": messages,
        },
        "model": {
            "provider": provider,
            "exact_snapshot": model_snapshot,
            "generation_parameters": {
                "temperature": temperature,
                "top_p": top_p,
                "max_tokens": max_tokens,
                "seed": seed,
                "seed_supported": seed_supported,
            },
        },
        "completion_instructions": (
            "This is request preparation only. After an actual recorded call, "
            "set status=completed and evidence_class=control; copy and "
            "complete all six *.template.json records without deleting failed, "
            "retried, or empty attempts."
        ),
    }
    templates = _bundle_templates(run_id, provider, model_snapshot)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    _write_json(output / "request.json", request)
    for filename, value in templates.items():
        _write_json(output / filename, value)
    summary = {
        "schema_version": 2,
        "run_id": run_id,
        "evidence_class": "control",
        "status": "protocol_template_not_experiment_output",
        "request": "request.json",
        "template_files": sorted(templates),
        "completed_bundle_files": list(REQUIRED_BUNDLE_FILES),
    }
    _write_json(output / "summary.json", summary)
    return summary


def _bundle_templates(
    run_id: str,
    provider: str,
    model_snapshot: str,
) -> dict[str, dict[str, Any]]:
    common = {
        "schema_version": 2,
        "run_id": run_id,
        "evidence_class": "protocol_template",
        "status": "template_not_completed",
    }
    return {
        "response.template.json": {
            **common,
            "model": {"provider": provider, "exact_snapshot": model_snapshot},
            "selected_attempt_id": "",
            "attempts": [],
        },
        "parsed_candidates.template.json": {
            **common,
            "parser": {"name": "", "version": ""},
            "selected_attempt_id": "",
            "candidates": [],
        },
        "ground_truth.template.json": {
            **common,
            "provenance": {
                "source_kind": "",
                "source_locator": "",
                "prepared_by": [],
                "prepared_at": "",
            },
            "items": [],
        },
        "review.template.json": {
            **common,
            "protocol_id": "mpsc-llm-human-review-v2",
            "reviewers": [],
            "decisions": [],
        },
        "evaluation.template.json": {
            **common,
            "computed_by": "mpsc-llm-evaluator-v2",
            "counts": {},
            "metrics_percent": {},
            "ground_truth_outcomes": [],
            "timing_seconds": {},
        },
        "timing.template.json": {
            **common,
            "stages_seconds": {},
            "stage_intervals": {},
            "attempts": [],
            "total_seconds": 0,
        },
        "redaction_log.template.json": {
            **common,
            "entries": [],
        },
    }


def prepare_subject_requests(
    output_root: str | Path,
    *,
    provider: str,
    model_snapshot: str,
    request_date: str,
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
    seed: int | None = None,
    seed_supported: bool = False,
    subjects_config: str | Path = DEFAULT_SUBJECT_CONFIG,
) -> dict[str, Any]:
    """Prepare request/template directories for all five frozen subjects."""

    config = yaml.safe_load(Path(subjects_config).read_text(encoding="utf-8"))
    subjects = config.get("subjects", [])
    if len(subjects) != 5:
        raise LLMProtocolError("subject config must contain exactly five subjects")
    root = Path(output_root)
    results = []
    for subject in subjects:
        source_path = Path(subject["source_path"])
        _, prompt_bytes = _load_prompt(DEFAULT_PROMPT_CONFIG)
        run_id = _prepared_run_id(
            subject["contract_id"],
            request_date,
            source_path.read_bytes(),
            prompt_bytes,
        )
        run_dir = root / subject["contract_id"] / run_id
        result = prepare_offline_run(
            source_path,
            run_dir,
            contract_id=subject["contract_id"],
            model_snapshot=model_snapshot,
            provider=provider,
            request_date=request_date,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            seed=seed,
            seed_supported=seed_supported,
        )
        results.append(
            {
                "contract_id": subject["contract_id"],
                "run_id": result["run_id"],
                "directory": run_dir.as_posix(),
            }
        )
    return {
        "schema_version": 2,
        "evidence_class": "control",
        "status": "prepared",
        "subjects": results,
    }


def _validate_common(filename: str, value: dict[str, Any], run_id: str) -> None:
    _require_fields(
        value,
        ("schema_version", "run_id", "evidence_class", "status"),
        filename,
    )
    if value["schema_version"] != 2:
        raise LLMProtocolError(f"{filename} schema_version must be 2")
    if value["run_id"] != run_id:
        raise LLMProtocolError(f"{filename} run_id differs from request.json")
    if value["evidence_class"] != "control":
        raise LLMProtocolError(f"{filename} evidence_class must be control")
    if value["status"] != "completed":
        raise LLMProtocolError(f"{filename} status must be completed")


def _validate_request(
    request: dict[str, Any],
    prompt_config: dict[str, Any],
    prompt_bytes: bytes,
) -> str:
    _require_fields(
        request,
        (
            "schema_version",
            "run_id",
            "evidence_class",
            "status",
            "request_date",
            "contract",
            "prompt",
            "model",
        ),
        "request.json",
    )
    run_id = _require_nonempty(request["run_id"], "request.run_id")
    _validate_common("request.json", request, run_id)
    _require_iso_date(request["request_date"], "request.request_date")

    contract = request["contract"]
    _require_fields(
        contract,
        ("id", "source_path", "source_sha256", "source_text"),
        "request.contract",
    )
    source_path = _require_nonempty(
        contract["source_path"], "request.contract.source_path"
    )
    if Path(source_path).is_absolute() or _WINDOWS_ABSOLUTE.search(source_path):
        raise LLMProtocolError("request contract source_path must be portable")
    if _sha256(contract["source_text"].encode()) != contract["source_sha256"]:
        raise LLMProtocolError("request contract source SHA-256 does not match")

    prompt = request["prompt"]
    _require_fields(
        prompt,
        (
            "template_id",
            "template_sha256",
            "system_template",
            "stages",
            "messages_in_provider_order",
        ),
        "request.prompt",
    )
    if prompt["template_id"] != prompt_config["template_id"]:
        raise LLMProtocolError("request uses an unknown prompt template_id")
    if prompt["template_sha256"] != _text_sha256(prompt_bytes):
        raise LLMProtocolError("request prompt template SHA-256 differs")
    if prompt["system_template"] != prompt_config["system_message"]:
        raise LLMProtocolError("request system template differs from frozen prompt")
    stages = prompt["stages"]
    if not isinstance(stages, list) or len(stages) != 3:
        raise LLMProtocolError("request must preserve three rendered prompt stages")
    delimiter = prompt_config["source_delimiter"]
    source_text = contract["source_text"]
    for stage, expected in zip(stages, prompt_config["stages"], strict=True):
        if stage.get("id") != expected["id"] or stage.get("role") != "user":
            raise LLMProtocolError("request prompt stage identity/order differs")
        if stage.get("template") != expected["instruction"]:
            raise LLMProtocolError("request prompt stage template differs")
        rendered = f"{expected['instruction']}\n\n{delimiter}\n{source_text}"
        if stage.get("rendered_content") != rendered:
            raise LLMProtocolError("request rendered prompt differs from template")
    messages = prompt["messages_in_provider_order"]
    if not isinstance(messages, list) or len(messages) != 4:
        raise LLMProtocolError("request must preserve all four messages in order")
    if [row.get("order") for row in messages] != [0, 1, 2, 3]:
        raise LLMProtocolError("request message order must be 0,1,2,3")
    if [row.get("role") for row in messages] != ["system", "user", "user", "user"]:
        raise LLMProtocolError("request roles must preserve system/user ordering")
    for row in messages:
        _require_nonempty(row.get("content"), "request message content")
    expected_contents = [prompt_config["system_message"]] + [
        stage["rendered_content"] for stage in stages
    ]
    if [row["content"] for row in messages] != expected_contents:
        raise LLMProtocolError("request provider messages differ from rendered prompt")

    model = request["model"]
    _require_fields(
        model,
        ("provider", "exact_snapshot", "generation_parameters"),
        "request.model",
    )
    provider = _require_nonempty(model["provider"], "request.model.provider")
    snapshot = _require_nonempty(
        model["exact_snapshot"], "request.model.exact_snapshot"
    )
    if provider.lower() in {"recorded", "provider", "unknown", "todo", "placeholder"}:
        raise LLMProtocolError("completed request has a placeholder provider")
    if snapshot.lower() in {"model", "unknown", "todo", "placeholder"}:
        raise LLMProtocolError("completed request has a placeholder model snapshot")
    generation = model["generation_parameters"]
    _require_fields(
        generation,
        ("temperature", "top_p", "max_tokens", "seed", "seed_supported"),
        "request.model.generation_parameters",
    )
    _require_number(
        generation["temperature"],
        "request.model.generation_parameters.temperature",
        minimum=0,
        maximum=2,
    )
    _require_number(
        generation["top_p"],
        "request.model.generation_parameters.top_p",
        minimum=0,
        maximum=1,
        minimum_inclusive=False,
    )
    max_tokens = generation["max_tokens"]
    if (
        isinstance(max_tokens, bool)
        or not isinstance(max_tokens, int)
        or max_tokens <= 0
    ):
        raise LLMProtocolError(
            "request.model.generation_parameters.max_tokens must be a positive integer"
        )
    seed_supported = generation["seed_supported"]
    seed = generation["seed"]
    if not isinstance(seed_supported, bool):
        raise LLMProtocolError(
            "request.model.generation_parameters.seed_supported must be boolean"
        )
    if seed_supported:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise LLMProtocolError(
                "completed seeded request must record an integer seed"
            )
    elif seed is not None:
        raise LLMProtocolError(
            "request records a seed although the provider/model does not support it"
        )
    return run_id


def _validate_response(
    response: dict[str, Any],
    request: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    _require_fields(
        response,
        ("model", "selected_attempt_id", "attempts"),
        "response.json",
    )
    if response["model"] != {
        "provider": request["model"]["provider"],
        "exact_snapshot": request["model"]["exact_snapshot"],
    }:
        raise LLMProtocolError("response model identity differs from request")
    attempts = response["attempts"]
    if not isinstance(attempts, list) or not attempts:
        raise LLMProtocolError("response must preserve at least one attempt")
    request_hash = _canonical_sha256(request)
    attempt_map: dict[str, dict[str, Any]] = {}
    for attempt in attempts:
        _require_fields(
            attempt,
            (
                "attempt_id",
                "request_sha256",
                "started_at",
                "completed_at",
                "status",
                "raw_response",
                "finish_reason",
                "usage",
                "failure",
            ),
            "response attempt",
        )
        attempt_id = _require_nonempty(attempt["attempt_id"], "attempt_id")
        if not _ATTEMPT_ID.fullmatch(attempt_id):
            raise LLMProtocolError(f"invalid stable attempt_id: {attempt_id}")
        if attempt_id in attempt_map:
            raise LLMProtocolError(f"duplicate attempt_id: {attempt_id}")
        _require_iso_datetime(attempt["started_at"], f"{attempt_id}.started_at")
        _require_iso_datetime(attempt["completed_at"], f"{attempt_id}.completed_at")
        if attempt["request_sha256"] != request_hash:
            raise LLMProtocolError(f"{attempt_id} request SHA-256 differs")
        status = attempt["status"]
        if status not in {"success", "failure", "empty_response"}:
            raise LLMProtocolError(f"{attempt_id} has invalid status")
        raw = attempt["raw_response"]
        if not isinstance(raw, str):
            raise LLMProtocolError(f"{attempt_id}.raw_response must be a string")
        if status == "success":
            if not raw.strip():
                raise LLMProtocolError(f"{attempt_id} success has no raw response")
            _require_nonempty(attempt["finish_reason"], f"{attempt_id}.finish_reason")
            usage = attempt["usage"]
            _require_fields(
                usage,
                ("input_tokens", "output_tokens", "total_tokens"),
                f"{attempt_id}.usage",
            )
            if any(not isinstance(usage[key], int) or usage[key] < 0 for key in usage):
                raise LLMProtocolError(f"{attempt_id} has invalid token usage")
            if usage["total_tokens"] != usage["input_tokens"] + usage["output_tokens"]:
                raise LLMProtocolError(f"{attempt_id} token total is inconsistent")
            if attempt["failure"] is not None:
                raise LLMProtocolError(f"{attempt_id} success cannot have failure data")
        elif status == "empty_response":
            if raw:
                raise LLMProtocolError(f"{attempt_id} empty_response is not empty")
            if attempt["failure"] is None:
                raise LLMProtocolError(
                    f"{attempt_id} empty_response needs a failure explanation"
                )
        elif attempt["failure"] is None:
            raise LLMProtocolError(f"{attempt_id} failure details are required")
        if status != "success":
            failure = attempt["failure"]
            if not isinstance(failure, dict):
                raise LLMProtocolError(f"{attempt_id} failure must be an object")
            _require_fields(
                failure,
                ("type", "message", "retryable"),
                f"{attempt_id}.failure",
            )
            _require_nonempty(failure["type"], f"{attempt_id}.failure.type")
            _require_nonempty(failure["message"], f"{attempt_id}.failure.message")
            if not isinstance(failure["retryable"], bool):
                raise LLMProtocolError(
                    f"{attempt_id}.failure.retryable must be boolean"
                )
        attempt_map[attempt_id] = attempt
    selected_id = response["selected_attempt_id"]
    if selected_id not in attempt_map:
        raise LLMProtocolError("selected_attempt_id is not a recorded attempt")
    selected = attempt_map[selected_id]
    if selected["status"] != "success":
        raise LLMProtocolError("selected attempt must have status success")
    return selected, attempt_map


def _validate_parsed(
    parsed: dict[str, Any],
    selected: dict[str, Any],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    _require_fields(
        parsed,
        ("parser", "selected_attempt_id", "candidates"),
        "parsed_candidates.json",
    )
    parser = parsed["parser"]
    _require_fields(parser, ("name", "version"), "parsed_candidates.parser")
    _require_nonempty(parser["name"], "parser.name")
    _require_nonempty(parser["version"], "parser.version")
    if parsed["selected_attempt_id"] != selected["attempt_id"]:
        raise LLMProtocolError("parsed candidate attempt differs from response")
    candidates = parsed["candidates"]
    if not isinstance(candidates, list):
        raise LLMProtocolError("parsed_candidates.candidates must be a list")
    required = list(config["candidate_required_fields"]) + ["source_trace"]
    field_contract = config.get("candidate_field_contract", {})
    string_fields = set(field_contract.get("nonempty_string", [])) - {"candidate_id"}
    collection_fields = set(field_contract.get("nonempty_list_or_object", []))
    if string_fields | collection_fields | {"candidate_id"} != set(
        config["candidate_required_fields"]
    ):
        raise LLMProtocolError(
            "prompt candidate field contract does not cover required fields"
        )
    seen: set[str] = set()
    raw = selected["raw_response"]

    def validate_collection(value: Any, label: str) -> None:
        if isinstance(value, str):
            _require_nonempty(value, label)
            return
        if isinstance(value, list):
            if not value:
                raise LLMProtocolError(f"{label} must not be empty")
            for index, entry in enumerate(value):
                validate_collection(entry, f"{label}[{index}]")
            return
        if isinstance(value, dict):
            if not value:
                raise LLMProtocolError(f"{label} must not be empty")
            for key, entry in value.items():
                _require_nonempty(key, f"{label} key")
                validate_collection(entry, f"{label}.{key}")
            return
        if value is None:
            raise LLMProtocolError(f"{label} must not be null")

    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise LLMProtocolError("every candidate must be an object")
        missing = [field for field in required if field not in candidate]
        if missing:
            raise LLMProtocolError(
                f"candidate {candidate.get('candidate_id', '<unknown>')} "
                f"is missing fields: {', '.join(missing)}"
            )
        candidate_id = candidate["candidate_id"]
        if not isinstance(candidate_id, str) or not _CANDIDATE_ID.fullmatch(
            candidate_id
        ):
            raise LLMProtocolError(f"invalid stable candidate_id: {candidate_id}")
        if candidate_id in seen:
            raise LLMProtocolError(f"duplicate candidate_id: {candidate_id}")
        seen.add(candidate_id)
        for field in string_fields:
            _require_nonempty(candidate[field], f"{candidate_id}.{field}")
        for field in collection_fields:
            values = candidate[field]
            if not isinstance(values, (list, dict)) or not values:
                raise LLMProtocolError(
                    f"{candidate_id}.{field} must be a non-empty list or object"
                )
            validate_collection(values, f"{candidate_id}.{field}")
        trace = candidate["source_trace"]
        _require_fields(
            trace,
            ("attempt_id", "start_char", "end_char", "exact_text"),
            f"{candidate_id}.source_trace",
        )
        if trace["attempt_id"] != selected["attempt_id"]:
            raise LLMProtocolError(f"{candidate_id} traces a non-selected attempt")
        _require_nonempty(
            trace["exact_text"], f"{candidate_id}.source_trace.exact_text"
        )
        start, end = trace["start_char"], trace["end_char"]
        valid_span = (
            isinstance(start, int)
            and not isinstance(start, bool)
            and isinstance(end, int)
            and not isinstance(end, bool)
            and 0 <= start < end
        )
        if not valid_span:
            raise LLMProtocolError(f"{candidate_id} has invalid source span")
        if end > len(raw) or raw[start:end] != trace["exact_text"]:
            raise LLMProtocolError(
                f"{candidate_id} source trace does not match raw response"
            )
    return candidates


def _validate_ground_truth(
    ground_truth: dict[str, Any],
) -> list[dict[str, Any]]:
    _require_fields(
        ground_truth,
        ("provenance", "items"),
        "ground_truth.json",
    )
    provenance = ground_truth["provenance"]
    _require_fields(
        provenance,
        (
            "source_kind",
            "source_locator",
            "prepared_by",
            "prepared_at",
        ),
        "ground_truth.provenance",
    )
    _require_nonempty(
        provenance["source_kind"], "ground_truth.provenance.source_kind"
    )
    _require_nonempty(
        provenance["source_locator"], "ground_truth.provenance.source_locator"
    )
    prepared_by = provenance["prepared_by"]
    if not isinstance(prepared_by, list) or not prepared_by:
        raise LLMProtocolError("ground truth requires pseudonymous preparer IDs")
    for reviewer_id in prepared_by:
        _validate_reviewer_id(reviewer_id)
    _require_iso_datetime(
        provenance["prepared_at"], "ground_truth.provenance.prepared_at"
    )

    items = ground_truth["items"]
    if not isinstance(items, list):
        raise LLMProtocolError("ground_truth.items must be a list")
    seen: set[str] = set()
    for item in items:
        _require_fields(
            item,
            ("ground_truth_id", "name", "source_locator", "rationale"),
            "ground-truth item",
        )
        truth_id = item["ground_truth_id"]
        if not isinstance(truth_id, str) or not _GROUND_TRUTH_ID.fullmatch(truth_id):
            raise LLMProtocolError(f"invalid stable ground_truth_id: {truth_id}")
        if truth_id in seen:
            raise LLMProtocolError(f"duplicate ground_truth_id: {truth_id}")
        seen.add(truth_id)
        _require_nonempty(item["name"], f"{truth_id}.name")
        _require_nonempty(item["source_locator"], f"{truth_id}.source_locator")
        _require_nonempty(item["rationale"], f"{truth_id}.rationale")
    return items


def _validate_reviewer_id(value: Any) -> str:
    reviewer_id = _require_nonempty(value, "pseudonymous reviewer ID")
    if not re.fullmatch(r"reviewer-[a-z0-9][a-z0-9_-]*", reviewer_id):
        raise LLMProtocolError(
            "reviewer IDs must be stable pseudonyms beginning `reviewer-`"
        )
    return reviewer_id


def _validate_review(
    review: dict[str, Any],
    candidate_ids: set[str],
    truth_ids: set[str],
    review_config: dict[str, Any],
) -> list[dict[str, Any]]:
    _require_fields(
        review,
        ("protocol_id", "reviewers", "decisions"),
        "review.json",
    )
    if review["protocol_id"] != review_config["protocol_id"]:
        raise LLMProtocolError("review protocol_id is not the frozen protocol")
    minimum_reviewers = review_config.get("minimum_independent_reviewers")
    if (
        isinstance(minimum_reviewers, bool)
        or not isinstance(minimum_reviewers, int)
        or minimum_reviewers < 2
    ):
        raise LLMProtocolError(
            "frozen review protocol requires at least two independent reviewers"
        )
    reviewers = review["reviewers"]
    if not isinstance(reviewers, list) or not reviewers:
        raise LLMProtocolError("review requires pseudonymous reviewers")
    for reviewer in reviewers:
        if not isinstance(reviewer, dict):
            raise LLMProtocolError("every reviewer must be an object")
        _require_fields(reviewer, ("reviewer_id", "role"), "reviewer")
    reviewer_ids = {_validate_reviewer_id(row["reviewer_id"]) for row in reviewers}
    if len(reviewer_ids) != len(reviewers):
        raise LLMProtocolError("reviewer IDs must be unique")
    reviewer_roles = {row["reviewer_id"]: row["role"] for row in reviewers}
    for reviewer in reviewers:
        if reviewer["role"] not in {"reviewer", "adjudicator"}:
            raise LLMProtocolError("reviewer role must be reviewer or adjudicator")

    decisions = review["decisions"]
    if not isinstance(decisions, list):
        raise LLMProtocolError("review.decisions must be a list")
    decision_ids = [row.get("candidate_id") for row in decisions]
    if set(decision_ids) != candidate_ids or len(decision_ids) != len(candidate_ids):
        raise LLMProtocolError("review must cover every candidate exactly once")
    matched_truth: set[str] = set()
    for decision in decisions:
        candidate_id = decision["candidate_id"]
        _require_fields(
            decision,
            ("candidate_id", "individual_reviews", "resolution"),
            f"review decision {candidate_id}",
        )
        individual = decision["individual_reviews"]
        if not isinstance(individual, list) or not individual:
            raise LLMProtocolError(f"{candidate_id} needs individual review")
        outcomes: set[tuple[str, str | None]] = set()
        voting_reviewer_ids: set[str] = set()
        for vote in individual:
            _require_fields(
                vote,
                (
                    "reviewer_id",
                    "decision",
                    "matched_ground_truth_id",
                    "rationale",
                    "reviewed_at",
                ),
                f"{candidate_id} individual review",
            )
            if vote["reviewer_id"] not in reviewer_ids:
                raise LLMProtocolError(f"{candidate_id} has an unknown reviewer")
            if reviewer_roles[vote["reviewer_id"]] != "reviewer":
                raise LLMProtocolError(
                    f"{candidate_id} adjudicator cannot cast an ordinary review vote"
                )
            if vote["reviewer_id"] in voting_reviewer_ids:
                raise LLMProtocolError(
                    f"{candidate_id} contains a duplicate reviewer vote"
                )
            voting_reviewer_ids.add(vote["reviewer_id"])
            if vote["decision"] not in {"accept", "reject"}:
                raise LLMProtocolError(f"{candidate_id} vote must accept or reject")
            vote_truth = vote["matched_ground_truth_id"]
            if vote["decision"] == "reject" and vote_truth is not None:
                raise LLMProtocolError(
                    f"{candidate_id} rejected vote cannot match ground truth"
                )
            if vote_truth is not None and vote_truth not in truth_ids:
                raise LLMProtocolError(
                    f"{candidate_id} vote matches unknown ground truth"
                )
            _require_nonempty(vote["rationale"], f"{candidate_id} vote rationale")
            _require_iso_datetime(vote["reviewed_at"], f"{candidate_id}.reviewed_at")
            outcomes.add((vote["decision"], vote_truth))
        if len(voting_reviewer_ids) < minimum_reviewers:
            raise LLMProtocolError(
                f"{candidate_id} requires at least {minimum_reviewers} "
                "independent reviewer votes"
            )
        resolution = decision["resolution"]
        _require_fields(
            resolution,
            (
                "final_decision",
                "matched_ground_truth_id",
                "rationale",
                "conflict_detected",
                "adjudication",
            ),
            f"{candidate_id} resolution",
        )
        final = resolution["final_decision"]
        if final not in {"accept", "reject"}:
            raise LLMProtocolError(f"{candidate_id} resolution must accept or reject")
        _require_nonempty(
            resolution["rationale"], f"{candidate_id} resolution rationale"
        )
        resolution_outcome = (
            resolution["final_decision"],
            resolution["matched_ground_truth_id"],
        )
        conflict = len(outcomes) > 1
        if resolution["conflict_detected"] is not conflict:
            raise LLMProtocolError(f"{candidate_id} conflict flag is inconsistent")
        adjudication = resolution["adjudication"]
        if not conflict and resolution_outcome not in outcomes:
            raise LLMProtocolError(
                f"{candidate_id} resolution outcome differs from unanimous reviews"
            )
        if conflict:
            if not isinstance(adjudication, dict):
                raise LLMProtocolError(f"{candidate_id} conflict needs adjudication")
            _require_fields(
                adjudication,
                (
                    "adjudicator_id",
                    "decided_at",
                    "final_decision",
                    "matched_ground_truth_id",
                    "rationale",
                ),
                f"{candidate_id} adjudication",
            )
            if adjudication["adjudicator_id"] not in reviewer_ids:
                raise LLMProtocolError(f"{candidate_id} adjudicator is unknown")
            if reviewer_roles[adjudication["adjudicator_id"]] != "adjudicator":
                raise LLMProtocolError(
                    f"{candidate_id} adjudicator lacks adjudicator role"
                )
            _require_iso_datetime(
                adjudication["decided_at"], f"{candidate_id}.adjudication.decided_at"
            )
            _require_nonempty(
                adjudication["rationale"], f"{candidate_id} adjudication rationale"
            )
            adjudicated_outcome = (
                adjudication["final_decision"],
                adjudication["matched_ground_truth_id"],
            )
            if adjudicated_outcome != resolution_outcome:
                raise LLMProtocolError(
                    f"{candidate_id} resolution differs from adjudicator outcome"
                )
        elif adjudication is not None:
            raise LLMProtocolError(
                f"{candidate_id} cannot contain adjudication without conflict"
            )
        truth_id = resolution["matched_ground_truth_id"]
        if final == "reject" and truth_id is not None:
            raise LLMProtocolError(f"{candidate_id} rejected candidate cannot match GT")
        if truth_id is not None:
            if truth_id not in truth_ids:
                raise LLMProtocolError(f"{candidate_id} matches unknown ground truth")
            if truth_id in matched_truth:
                raise LLMProtocolError(
                    f"ground truth {truth_id} is matched more than once"
                )
            matched_truth.add(truth_id)
    return decisions


def _validate_timing(
    timing: dict[str, Any],
    attempt_map: dict[str, dict[str, Any]],
) -> dict[str, float]:
    _require_fields(
        timing,
        ("stages_seconds", "stage_intervals", "attempts", "total_seconds"),
        "timing.json",
    )
    required_stages = (
        "preparation",
        "provider_interaction",
        "parsing",
        "human_review",
        "adjudication",
    )
    stages = timing["stages_seconds"]
    _require_fields(stages, required_stages, "timing.stages_seconds")
    if any(
        not isinstance(stages[key], (int, float)) or stages[key] < 0
        for key in required_stages
    ):
        raise LLMProtocolError("timing stage values must be non-negative numbers")
    intervals = timing["stage_intervals"]
    _require_fields(intervals, required_stages, "timing.stage_intervals")
    for stage_id in required_stages:
        interval = intervals[stage_id]
        _require_fields(
            interval,
            ("started_at", "completed_at", "duration_seconds"),
            f"timing.stage_intervals.{stage_id}",
        )
        started = _require_iso_datetime(
            interval["started_at"], f"{stage_id}.started_at"
        )
        completed = _require_iso_datetime(
            interval["completed_at"], f"{stage_id}.completed_at"
        )
        elapsed = (completed - started).total_seconds()
        if elapsed < 0:
            raise LLMProtocolError(f"{stage_id} timing ends before it starts")
        if (
            not isinstance(interval["duration_seconds"], (int, float))
            or abs(elapsed - float(interval["duration_seconds"])) > 1e-6
            or abs(elapsed - float(stages[stage_id])) > 1e-6
        ):
            raise LLMProtocolError(
                f"{stage_id} timing differs from its timestamp interval"
            )
    total = sum(float(stages[key]) for key in required_stages)
    if (
        not isinstance(timing["total_seconds"], (int, float))
        or abs(total - float(timing["total_seconds"])) > 1e-6
    ):
        raise LLMProtocolError("timing total does not equal stage timings")
    timing_attempts = timing["attempts"]
    if not isinstance(timing_attempts, list):
        raise LLMProtocolError("timing.attempts must be a list")
    timing_ids = {row.get("attempt_id") for row in timing_attempts}
    if timing_ids != set(attempt_map) or len(timing_attempts) != len(attempt_map):
        raise LLMProtocolError("timing must preserve every response attempt")
    provider_seconds = 0.0
    for row in timing_attempts:
        _require_fields(
            row,
            ("attempt_id", "status", "duration_seconds"),
            "timing attempt",
        )
        recorded = attempt_map[row["attempt_id"]]
        if row["status"] != recorded["status"]:
            raise LLMProtocolError("timing attempt status differs from response")
        duration = row["duration_seconds"]
        if not isinstance(duration, (int, float)) or duration < 0:
            raise LLMProtocolError("attempt duration must be non-negative")
        started = _require_iso_datetime(
            recorded["started_at"], f"{row['attempt_id']}.started_at"
        )
        completed = _require_iso_datetime(
            recorded["completed_at"], f"{row['attempt_id']}.completed_at"
        )
        elapsed = (completed - started).total_seconds()
        if elapsed < 0 or abs(elapsed - float(duration)) > 1e-6:
            raise LLMProtocolError(
                f"{row['attempt_id']} duration differs from response timestamps"
            )
        provider_seconds += float(duration)
    if abs(provider_seconds - float(stages["provider_interaction"])) > 1e-6:
        raise LLMProtocolError(
            "provider interaction timing does not equal recorded attempts"
        )
    return {key: float(stages[key]) for key in required_stages} | {"total": total}


def _computed_evaluation(
    run_id: str,
    candidates: list[dict[str, Any]],
    ground_truth: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    timings: dict[str, float],
) -> dict[str, Any]:
    accepted = [
        row for row in decisions if row["resolution"]["final_decision"] == "accept"
    ]
    truth_ids = {row["ground_truth_id"] for row in ground_truth}
    matched = {
        row["resolution"]["matched_ground_truth_id"]
        for row in accepted
        if row["resolution"]["matched_ground_truth_id"] is not None
    }
    true_positive = len(matched)
    false_positive = len(accepted) - true_positive
    false_negative = len(truth_ids - matched)
    precision = true_positive / len(accepted) if accepted else 0.0
    recall = true_positive / len(truth_ids) if truth_ids else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    outcomes = [
        {
            "ground_truth_id": truth_id,
            "outcome": "matched" if truth_id in matched else "false_negative",
            "matched_candidate_id": next(
                (
                    row["candidate_id"]
                    for row in accepted
                    if row["resolution"]["matched_ground_truth_id"] == truth_id
                ),
                None,
            ),
        }
        for truth_id in sorted(truth_ids)
    ]
    return {
        "schema_version": 2,
        "run_id": run_id,
        "evidence_class": "control",
        "status": "completed",
        "computed_by": "mpsc-llm-evaluator-v2",
        "counts": {
            "ground_truth": len(truth_ids),
            "llm_candidates": len(candidates),
            "human_accepted": len(accepted),
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
        },
        "metrics_percent": {
            "precision": round(100 * precision, 6),
            "recall": round(100 * recall, 6),
            "f1": round(100 * f1, 6),
        },
        "ground_truth_outcomes": outcomes,
        "timing_seconds": timings,
    }


def _validate_redaction_log(root: Path, run_id: str) -> None:
    path = root / "redaction_log.json"
    if not path.exists():
        return
    value = _load_json(path)
    _validate_common("redaction_log.json", value, run_id)
    entries = value.get("entries")
    if not isinstance(entries, list):
        raise LLMProtocolError("redaction_log.entries must be a list")
    for entry in entries:
        _require_fields(
            entry,
            (
                "artifact",
                "json_path",
                "reason",
                "original_sha256",
                "redacted_sha256",
                "affects_candidate_spans",
            ),
            "redaction entry",
        )
        if entry["artifact"] in PROTECTED_REDACTION_FILES:
            raise LLMProtocolError(
                f"redaction may not alter {entry['artifact']} evidence"
            )
        artifact_path = root / entry["artifact"]
        if not artifact_path.is_file() or artifact_path.parent != root:
            raise LLMProtocolError("redaction artifact must be a bundle-root file")
        if entry["affects_candidate_spans"] is not False:
            raise LLMProtocolError("redaction may not alter candidate source spans")
        _require_nonempty(entry["reason"], "redaction reason")
        for key in ("original_sha256", "redacted_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", str(entry[key])):
                raise LLMProtocolError(f"redaction {key} must be SHA-256")
        if entry["original_sha256"] == entry["redacted_sha256"]:
            raise LLMProtocolError("redaction before/after hashes must differ")
        if _sha256(artifact_path.read_bytes()) != entry["redacted_sha256"]:
            raise LLMProtocolError(
                "redaction redacted_sha256 differs from the published artifact"
            )


def verify_recorded_run(
    run_dir: str | Path,
    *,
    prompt_config: str | Path = DEFAULT_PROMPT_CONFIG,
    review_config: str | Path = DEFAULT_REVIEW_CONFIG,
) -> dict[str, Any]:
    """Read and verify a completed seven-file bundle without modifying it."""

    root = Path(run_dir)
    records = {name: _load_json(root / name) for name in REQUIRED_BUNDLE_FILES}
    prompt, prompt_bytes = _load_prompt(Path(prompt_config))
    run_id = _validate_request(records["request.json"], prompt, prompt_bytes)
    for filename, value in records.items():
        _validate_common(filename, value, run_id)
        _check_sensitive_content(filename, value)
    _validate_redaction_log(root, run_id)
    if (root / "redaction_log.json").exists():
        _check_sensitive_content(
            "redaction_log.json", _load_json(root / "redaction_log.json")
        )

    selected, attempt_map = _validate_response(
        records["response.json"], records["request.json"]
    )
    candidates = _validate_parsed(records["parsed_candidates.json"], selected, prompt)
    ground_truth = _validate_ground_truth(records["ground_truth.json"])
    review_protocol = yaml.safe_load(Path(review_config).read_text(encoding="utf-8"))
    decisions = _validate_review(
        records["review.json"],
        {row["candidate_id"] for row in candidates},
        {row["ground_truth_id"] for row in ground_truth},
        review_protocol,
    )
    timings = _validate_timing(records["timing.json"], attempt_map)
    has_adjudication = any(row["resolution"]["conflict_detected"] for row in decisions)
    if has_adjudication and timings["adjudication"] <= 0:
        raise LLMProtocolError(
            "conflicted reviews require a positive adjudication timing"
        )
    if not has_adjudication and timings["adjudication"] != 0:
        raise LLMProtocolError(
            "adjudication timing must be zero when no conflict was adjudicated"
        )
    computed = _computed_evaluation(
        run_id,
        candidates,
        ground_truth,
        decisions,
        timings,
    )
    if records["evaluation.json"] != computed:
        raise LLMProtocolError(
            "evaluation.json differs from candidate-level computation"
        )
    return {
        "schema_version": 2,
        "run_id": run_id,
        "evidence_class": "control",
        "status": "pass",
        "verified_files": list(REQUIRED_BUNDLE_FILES),
        "redaction_log_present": (root / "redaction_log.json").exists(),
        "computed_evaluation": computed,
    }


def evaluate_recorded_run(
    run_dir: str | Path,
    *,
    prompt_config: str | Path = DEFAULT_PROMPT_CONFIG,
) -> dict[str, Any]:
    """Compatibility alias for the now strictly read-only verifier."""

    return verify_recorded_run(run_dir, prompt_config=prompt_config)
