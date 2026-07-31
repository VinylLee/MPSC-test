"""Verify the published GPT-5 LLM outputs without modifying them."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SESSION_ROOT = REPOSITORY_ROOT / "experiment-data/llm/gpt5_session"
SUBJECTS_ROOT = SESSION_ROOT / "subjects"
EXPECTED_RUN_ID = "gpt5"
EXPECTED_SUBJECTS = {
    "mytoken": "MYT",
    "rubixi": "RUB",
    "bectoken": "BEC",
    "gnosissafeproxy": "GSP",
    "personal_bank": "PBK",
}
EXPECTED_SOURCE_PATHS = {
    "mytoken": "experiment-data/subjects/MyToken.sol",
    "rubixi": "experiment-data/subjects/Rubixi/Rubixi.sol",
    "bectoken": "experiment-data/subjects/BecToken/BecToken.sol",
    "gnosissafeproxy": ("experiment-data/subjects/GnosisSafeProxy/GnosisSafeProxy.sol"),
    "personal_bank": ("experiment-data/subjects/PERSONAL_BANK/PERSONAL_BANK.sol"),
}
REQUIRED_CANDIDATE_FIELDS = (
    "candidate_id",
    "name",
    "source",
    "parameter_type",
    "feasible_values",
    "valid_perturbations",
    "boundary_perturbations",
    "invalid_perturbations",
    "affected_operation",
    "affected_state",
    "observable_outcomes",
)
LIST_FIELDS = {
    "feasible_values",
    "valid_perturbations",
    "boundary_perturbations",
    "invalid_perturbations",
    "observable_outcomes",
}


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: top-level value must be an object")
    return value


def _lf_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _check_candidate(
    candidate: Any,
    *,
    subject_id: str,
    prefix: str,
    index: int,
    errors: list[str],
) -> str | None:
    location = f"{subject_id}.candidates[{index}]"
    if not isinstance(candidate, dict):
        errors.append(f"{location}: must be an object")
        return None

    for field in REQUIRED_CANDIDATE_FIELDS:
        if field not in candidate:
            errors.append(f"{location}.{field}: missing")
            continue
        value = candidate[field]
        if field in LIST_FIELDS:
            if not isinstance(value, list) or not value:
                errors.append(f"{location}.{field}: must be a non-empty list")
            elif any(
                item is None
                or isinstance(item, (dict, list))
                or (isinstance(item, str) and not item.strip())
                for item in value
            ):
                errors.append(f"{location}.{field}: contains an empty/complex item")
        elif not _nonempty_string(value):
            errors.append(f"{location}.{field}: must be a non-empty string")

    candidate_id = candidate.get("candidate_id")
    if not _nonempty_string(candidate_id):
        return None
    if re.fullmatch(rf"{re.escape(prefix)}-C\d{{3}}", candidate_id) is None:
        errors.append(
            f"{location}.candidate_id: expected {prefix}-C followed by three digits"
        )
    return candidate_id


def verify() -> dict[str, Any]:
    errors: list[str] = []
    candidate_count = 0
    response_files = {
        path.parent.name: path
        for path in SUBJECTS_ROOT.glob("*/response.json")
        if path.is_file()
    }
    expected_ids = set(EXPECTED_SUBJECTS)
    actual_ids = set(response_files)
    if actual_ids != expected_ids:
        errors.append(
            "subjects: expected exactly "
            f"{sorted(expected_ids)}, got {sorted(actual_ids)}"
        )

    completed_subjects = 0
    for subject_id, prefix in EXPECTED_SUBJECTS.items():
        source_path = EXPECTED_SOURCE_PATHS[subject_id]
        source = REPOSITORY_ROOT / source_path
        response_file = response_files.get(subject_id)
        if not source.is_file():
            errors.append(f"{subject_id}: source file not found: {source_path}")
            continue
        actual_hash = _lf_sha256(source)
        if response_file is None:
            errors.append(f"{subject_id}: response file not found")
            continue

        try:
            response = _load_json(response_file)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            errors.append(str(error))
            continue

        expected_response_values = {
            "schema_version": 1,
            "run_id": EXPECTED_RUN_ID,
            "subject_id": subject_id,
        }
        for field, expected in expected_response_values.items():
            if response.get(field) != expected:
                errors.append(
                    f"{subject_id}.{field}: expected {expected!r}, "
                    f"got {response.get(field)!r}"
                )
        for field in ("status", "independent_review_status"):
            if field in response:
                errors.append(f"{subject_id}.{field}: field must be absent")
        if not _nonempty_string(response.get("generated_at")):
            errors.append(f"{subject_id}.generated_at: must be a non-empty string")

        request = response.get("request")
        if not isinstance(request, dict):
            errors.append(f"{subject_id}.request: must be an object")
        else:
            if request.get("prompt_template") != (
                "code/configs/llm/mutable_parameter_prompt.yaml"
            ):
                errors.append(f"{subject_id}.request.prompt_template: unexpected")
            if request.get("source_path") != source_path:
                errors.append(f"{subject_id}.request.source_path: mismatch")
            if request.get("source_sha256") != actual_hash:
                errors.append(f"{subject_id}.request.source_sha256: mismatch")

        raw_response = response.get("response")
        if not isinstance(raw_response, dict):
            errors.append(f"{subject_id}.response: must be an object")
            continue
        if raw_response.get("raw_output_format") != "application/json":
            errors.append(f"{subject_id}.response.raw_output_format: unexpected")
        candidates = raw_response.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            errors.append(f"{subject_id}.response.candidates: non-empty list required")
            continue

        candidate_count += len(candidates)
        seen_candidate_ids: set[str] = set()
        for index, candidate in enumerate(candidates):
            candidate_id = _check_candidate(
                candidate,
                subject_id=subject_id,
                prefix=prefix,
                index=index,
                errors=errors,
            )
            if candidate_id in seen_candidate_ids:
                errors.append(f"{subject_id}: duplicate candidate_id {candidate_id}")
            if candidate_id is not None:
                seen_candidate_ids.add(candidate_id)
        completed_subjects += 1

    return {
        "status": "pass" if not errors else "fail",
        "output_count": completed_subjects,
        "candidate_count": candidate_count,
        "errors": errors,
    }


def main() -> int:
    result = verify()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
