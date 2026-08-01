import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner
from mpsc.cli import main
from mpsc.llm import (
    LLMProtocolError,
    prepare_offline_run,
    prepare_subject_requests,
    verify_recorded_run,
)


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _canonical_hash(value):
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _candidate(raw: str):
    exact = "recipient"
    start = raw.index(exact)
    return {
        "candidate_id": "C001",
        "name": "to",
        "source": "function argument",
        "parameter_type": "address",
        "feasible_values": ["account[1]"],
        "valid_perturbations": ["another funded account"],
        "boundary_perturbations": ["zero address"],
        "invalid_perturbations": ["malformed address"],
        "affected_operation": "transfer",
        "affected_state": "balances",
        "observable_outcomes": ["receipt status", "balances"],
        "source_trace": {
            "attempt_id": "A001",
            "start_char": start,
            "end_char": start + len(exact),
            "exact_text": exact,
        },
    }


def _complete_bundle(tmp_path: Path) -> Path:
    source = tmp_path / "Sample.sol"
    source.write_text("contract Sample {}", encoding="utf-8")
    run = tmp_path / "run"
    prepare_offline_run(
        source,
        run,
        contract_id="Sample",
        provider="example-provider",
        model_snapshot="example-model-",
        request_date="2025-01-01",
        temperature=0,
        top_p=1,
        max_tokens=1000,
        seed=7,
        seed_supported=True,
    )
    request = _read(run / "request.json")
    request["evidence_class"] = "control"
    request["status"] = "completed"
    _write(run / "request.json", request)

    raw = "Candidate: the transfer recipient is externally controllable."
    common = {
        "schema_version": 2,
        "run_id": request["run_id"],
        "evidence_class": "control",
        "status": "completed",
    }
    _write(
        run / "response.json",
        {
            **common,
            "model": {
                "provider": "example-provider",
                "exact_snapshot": "example-model-",
            },
            "selected_attempt_id": "A001",
            "attempts": [
                {
                    "attempt_id": "A001",
                    "request_sha256": _canonical_hash(request),
                    "started_at": "2025-01-01T10:00:00+08:00",
                    "completed_at": "2025-01-01T10:00:02+08:00",
                    "status": "success",
                    "raw_response": raw,
                    "finish_reason": "stop",
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 20,
                        "total_tokens": 120,
                    },
                    "failure": None,
                }
            ],
        },
    )
    _write(
        run / "parsed_candidates.json",
        {
            **common,
            "parser": {"name": "manual-json-parser", "version": "1.0.0"},
            "selected_attempt_id": "A001",
            "candidates": [_candidate(raw)],
        },
    )
    _write(
        run / "ground_truth.json",
        {
            **common,
            "provenance": {
                "source_kind": "independent_manual_source_analysis",
                "source_locator": "review-workbook-v1#Sample",
                "prepared_by": ["reviewer-ground-truth-1"],
                "prepared_at": "2025-01-01T09:00:00+08:00",
            },
            "items": [
                {
                    "ground_truth_id": "GT001",
                    "name": "to",
                    "source_locator": "Sample.sol:transfer(to)",
                    "rationale": "The caller supplies the address.",
                },
                {
                    "ground_truth_id": "GT002",
                    "name": "caller",
                    "source_locator": "Sample.sol:msg.sender",
                    "rationale": "The invoking account is externally variable.",
                },
            ],
        },
    )
    _write(
        run / "review.json",
        {
            **common,
            "protocol_id": "mpsc-llm-human-review-v2",
            "reviewers": [
                {"reviewer_id": "reviewer-1", "role": "reviewer"},
                {"reviewer_id": "reviewer-2", "role": "reviewer"},
            ],
            "decisions": [
                {
                    "candidate_id": "C001",
                    "individual_reviews": [
                        {
                            "reviewer_id": "reviewer-1",
                            "decision": "accept",
                            "matched_ground_truth_id": "GT001",
                            "rationale": "Externally controllable.",
                            "reviewed_at": "2025-01-01T11:00:00+08:00",
                        },
                        {
                            "reviewer_id": "reviewer-2",
                            "decision": "accept",
                            "matched_ground_truth_id": "GT001",
                            "rationale": "Matches the source parameter.",
                            "reviewed_at": "2025-01-01T11:01:00+08:00",
                        },
                    ],
                    "resolution": {
                        "final_decision": "accept",
                        "matched_ground_truth_id": "GT001",
                        "rationale": "Both reviewers accepted the candidate.",
                        "conflict_detected": False,
                        "adjudication": None,
                    },
                }
            ],
        },
    )
    timings = {
        "preparation": 1.0,
        "provider_interaction": 2.0,
        "parsing": 1.0,
        "human_review": 3.0,
        "adjudication": 0.0,
        "total": 7.0,
    }
    _write(
        run / "timing.json",
        {
            **common,
            "stages_seconds": {
                key: value for key, value in timings.items() if key != "total"
            },
            "stage_intervals": {
                "preparation": {
                    "started_at": "2025-01-01T09:59:58+08:00",
                    "completed_at": "2025-01-01T09:59:59+08:00",
                    "duration_seconds": 1.0,
                },
                "provider_interaction": {
                    "started_at": "2025-01-01T10:00:00+08:00",
                    "completed_at": "2025-01-01T10:00:02+08:00",
                    "duration_seconds": 2.0,
                },
                "parsing": {
                    "started_at": "2025-01-01T10:00:02+08:00",
                    "completed_at": "2025-01-01T10:00:03+08:00",
                    "duration_seconds": 1.0,
                },
                "human_review": {
                    "started_at": "2025-01-01T11:00:00+08:00",
                    "completed_at": "2025-01-01T11:00:03+08:00",
                    "duration_seconds": 3.0,
                },
                "adjudication": {
                    "started_at": "2025-01-01T11:00:03+08:00",
                    "completed_at": "2025-01-01T11:00:03+08:00",
                    "duration_seconds": 0.0,
                },
            },
            "attempts": [
                {
                    "attempt_id": "A001",
                    "status": "success",
                    "duration_seconds": 2.0,
                }
            ],
            "total_seconds": 7.0,
        },
    )
    _write(
        run / "evaluation.json",
        {
            **common,
            "computed_by": "mpsc-llm-evaluator-v2",
            "counts": {
                "ground_truth": 2,
                "llm_candidates": 1,
                "human_accepted": 1,
                "true_positive": 1,
                "false_positive": 0,
                "false_negative": 1,
            },
            "metrics_percent": {
                "precision": 100.0,
                "recall": 50.0,
                "f1": 66.666667,
            },
            "ground_truth_outcomes": [
                {
                    "ground_truth_id": "GT001",
                    "outcome": "matched",
                    "matched_candidate_id": "C001",
                },
                {
                    "ground_truth_id": "GT002",
                    "outcome": "false_negative",
                    "matched_candidate_id": None,
                },
            ],
            "timing_seconds": timings,
        },
    )
    return run


def _snapshot(directory: Path):
    return {
        path.name: path.read_bytes() for path in directory.iterdir() if path.is_file()
    }


def test_prompt_and_protocol_are_frozen_and_disclose_provenance():
    prompt = yaml.safe_load(
        Path("code/configs/llm/mutable_parameter_prompt.yaml").read_text(
            encoding="utf-8"
        )
    )
    bundle = yaml.safe_load(
        Path("code/configs/llm/bundle_contract.yaml").read_text(encoding="utf-8")
    )
    subjects = yaml.safe_load(
        Path("code/configs/llm/control_run_subjects.yaml").read_text(encoding="utf-8")
    )
    review_protocol = yaml.safe_load(
        Path("code/configs/llm/reviewer_protocol.yaml").read_text(encoding="utf-8")
    )
    assert [row["id"] for row in prompt["stages"]] == [
        "execution_factor_extraction",
        "deployment_environment_analysis",
        "smart_contract_function_calling_analysis",
    ]
    assert bundle["completed_evidence_class"] == "control"
    assert len(bundle["required_files"]) == 7
    assert len(subjects["subjects"]) == 5
    assert review_protocol["minimum_independent_reviewers"] == 2


def test_prepare_is_deterministic_network_free_and_cannot_look_completed(tmp_path):
    source = tmp_path / "Sample.sol"
    source.write_text("contract Sample {}", encoding="utf-8")
    kwargs = {
        "contract_id": "Sample",
        "provider": "example-provider",
        "model_snapshot": "example-model-",
        "request_date": "2025-01-01",
    }
    first = prepare_offline_run(source, tmp_path / "a", **kwargs)
    second = prepare_offline_run(source, tmp_path / "b", **kwargs)
    assert first["run_id"] == second["run_id"]
    assert first["status"] == "protocol_template_not_experiment_output"
    assert len(first["completed_bundle_files"]) == 7
    request = _read(tmp_path / "a/request.json")
    assert request["evidence_class"] == "control"
    assert request["status"] == "prepared_not_executed"
    message_order = [
        row["order"] for row in request["prompt"]["messages_in_provider_order"]
    ]
    assert message_order == [0, 1, 2, 3]
    assert not Path(request["contract"]["source_path"]).is_absolute()
    with pytest.raises(LLMProtocolError, match="response.json"):
        verify_recorded_run(tmp_path / "a")


def test_prepare_all_five_subjects_uses_frozen_inputs(tmp_path):
    result = prepare_subject_requests(
        tmp_path / "five",
        provider="example-provider",
        model_snapshot="example-model-",
        request_date="2025-01-01",
    )
    assert result["status"] == "prepared"
    assert {row["contract_id"] for row in result["subjects"]} == {
        "MyToken",
        "Rubixi",
        "BecToken",
        "GnosisSafeProxy",
        "PERSONAL_BANK",
    }
    assert all(
        Path(row["directory"]).joinpath("request.json").is_file()
        for row in result["subjects"]
    )


def test_complete_synthetic_fixture_computes_and_is_read_only(tmp_path):
    run = _complete_bundle(tmp_path)
    before = _snapshot(run)
    result = verify_recorded_run(run)
    after = _snapshot(run)
    assert result["status"] == "pass"
    assert result["computed_evaluation"]["counts"]["false_negative"] == 1
    assert result["computed_evaluation"]["metrics_percent"]["f1"] == 66.666667
    assert before == after


def test_missing_raw_response_is_rejected(tmp_path):
    run = _complete_bundle(tmp_path)
    response = _read(run / "response.json")
    response["attempts"][0]["raw_response"] = ""
    _write(run / "response.json", response)
    with pytest.raises(LLMProtocolError, match="success has no raw response"):
        verify_recorded_run(run)


def test_candidate_without_source_trace_is_rejected(tmp_path):
    run = _complete_bundle(tmp_path)
    parsed = _read(run / "parsed_candidates.json")
    del parsed["candidates"][0]["source_trace"]
    _write(run / "parsed_candidates.json", parsed)
    with pytest.raises(LLMProtocolError, match="source_trace"):
        verify_recorded_run(run)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", ""),
        ("source", None),
        ("parameter_type", " "),
        ("affected_operation", []),
        ("affected_state", None),
        ("feasible_values", []),
        ("valid_perturbations", None),
        ("boundary_perturbations", {}),
        ("invalid_perturbations", [""]),
        ("observable_outcomes", [None]),
    ],
)
def test_candidate_semantic_fields_must_be_typed_and_nonempty(tmp_path, field, value):
    run = _complete_bundle(tmp_path)
    parsed = _read(run / "parsed_candidates.json")
    parsed["candidates"][0][field] = value
    _write(run / "parsed_candidates.json", parsed)
    with pytest.raises(LLMProtocolError, match=field):
        verify_recorded_run(run)


def test_candidate_without_review_is_rejected(tmp_path):
    run = _complete_bundle(tmp_path)
    review = _read(run / "review.json")
    review["decisions"] = []
    _write(run / "review.json", review)
    with pytest.raises(LLMProtocolError, match="cover every candidate"):
        verify_recorded_run(run)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda review: review["decisions"][0]["individual_reviews"].pop(),
            "at least 2 independent reviewer votes",
        ),
        (
            lambda review: review["decisions"][0]["individual_reviews"][1].update(
                {"reviewer_id": "reviewer-1"}
            ),
            "duplicate reviewer vote",
        ),
        (
            lambda review: (
                review["reviewers"].append(
                    {"reviewer_id": "reviewer-3", "role": "adjudicator"}
                ),
                review["decisions"][0]["individual_reviews"][1].update(
                    {"reviewer_id": "reviewer-3"}
                ),
            ),
            "adjudicator cannot cast",
        ),
        (
            lambda review: review["decisions"][0]["individual_reviews"][1].update(
                {"matched_ground_truth_id": "GT002"}
            ),
            "conflict flag is inconsistent",
        ),
        (
            lambda review: review["decisions"][0]["resolution"].update(
                {"matched_ground_truth_id": "GT002"}
            ),
            "resolution outcome differs",
        ),
    ],
)
def test_review_requires_independent_roles_and_complete_outcome_agreement(
    tmp_path, mutate, message
):
    run = _complete_bundle(tmp_path)
    review = _read(run / "review.json")
    mutate(review)
    _write(run / "review.json", review)
    with pytest.raises(LLMProtocolError, match=message):
        verify_recorded_run(run)


def test_conflict_requires_role_adjudicator_recorded_outcome(tmp_path):
    run = _complete_bundle(tmp_path)
    review = _read(run / "review.json")
    review["decisions"][0]["individual_reviews"][1]["matched_ground_truth_id"] = "GT002"
    review["decisions"][0]["resolution"]["conflict_detected"] = True
    _write(run / "review.json", review)
    with pytest.raises(LLMProtocolError, match="conflict needs adjudication"):
        verify_recorded_run(run)


def test_role_adjudicator_can_resolve_full_outcome_conflict(tmp_path):
    run = _complete_bundle(tmp_path)
    review = _read(run / "review.json")
    review["reviewers"].append({"reviewer_id": "reviewer-3", "role": "adjudicator"})
    review["decisions"][0]["individual_reviews"][1]["matched_ground_truth_id"] = "GT002"
    resolution = review["decisions"][0]["resolution"]
    resolution["conflict_detected"] = True
    resolution["adjudication"] = {
        "adjudicator_id": "reviewer-3",
        "decided_at": "2025-01-01T11:02:00+08:00",
        "final_decision": "accept",
        "matched_ground_truth_id": "GT001",
        "rationale": "The first source locator is the exact parameter match.",
    }
    _write(run / "review.json", review)
    timing = _read(run / "timing.json")
    timing["stages_seconds"]["adjudication"] = 1.0
    timing["stage_intervals"]["adjudication"] = {
        "started_at": "2025-01-01T11:02:00+08:00",
        "completed_at": "2025-01-01T11:02:01+08:00",
        "duration_seconds": 1.0,
    }
    timing["total_seconds"] = 8.0
    _write(run / "timing.json", timing)
    evaluation = _read(run / "evaluation.json")
    evaluation["timing_seconds"]["adjudication"] = 1.0
    evaluation["timing_seconds"]["total"] = 8.0
    _write(run / "evaluation.json", evaluation)
    assert verify_recorded_run(run)["status"] == "pass"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("temperature", None, "temperature must be a number"),
        ("temperature", float("nan"), "temperature must be a finite number"),
        ("temperature", -0.1, "temperature must be in"),
        ("top_p", None, "top_p must be a number"),
        ("top_p", 0, "top_p must be in"),
        ("top_p", 1.1, "top_p must be in"),
        ("max_tokens", None, "max_tokens must be a positive integer"),
        ("max_tokens", 0, "max_tokens must be a positive integer"),
        ("seed_supported", "yes", "seed_supported must be boolean"),
    ],
)
def test_completed_request_requires_concrete_generation_parameters(
    tmp_path, field, value, message
):
    run = _complete_bundle(tmp_path)
    request = _read(run / "request.json")
    request["model"]["generation_parameters"][field] = value
    _write(run / "request.json", request)
    with pytest.raises(LLMProtocolError, match=message):
        verify_recorded_run(run)


@pytest.mark.parametrize(
    ("seed_supported", "seed", "message"),
    [
        (True, None, "must record an integer seed"),
        (False, 7, "does not support"),
        (True, "7", "must record an integer seed"),
    ],
)
def test_completed_request_seed_support_and_value_must_agree(
    tmp_path, seed_supported, seed, message
):
    run = _complete_bundle(tmp_path)
    request = _read(run / "request.json")
    generation = request["model"]["generation_parameters"]
    generation["seed_supported"] = seed_supported
    generation["seed"] = seed
    _write(run / "request.json", request)
    with pytest.raises(LLMProtocolError, match=message):
        verify_recorded_run(run)


@pytest.mark.parametrize(
    ("filename", "mutate", "message"),
    [
        (
            "evaluation.json",
            lambda value: value["ground_truth_outcomes"].pop(),
            "candidate-level computation",
        ),
        (
            "evaluation.json",
            lambda value: value["counts"].update({"true_positive": 2}),
            "candidate-level computation",
        ),
        (
            "timing.json",
            lambda value: value.update({"total_seconds": 99}),
            "timing total",
        ),
        (
            "timing.json",
            lambda value: value["stage_intervals"]["parsing"].update(
                {"completed_at": "2025-01-01T10:00:09+08:00"}
            ),
            "parsing timing differs",
        ),
    ],
)
def test_ground_truth_evaluation_and_timing_tamper_are_rejected(
    tmp_path, filename, mutate, message
):
    run = _complete_bundle(tmp_path)
    value = _read(run / filename)
    mutate(value)
    _write(run / filename, value)
    with pytest.raises(LLMProtocolError, match=message):
        verify_recorded_run(run)


def test_template_cannot_masquerade_as_completed_output(tmp_path):
    run = _complete_bundle(tmp_path)
    response = _read(run / "response.json")
    response["evidence_class"] = "protocol_template"
    response["status"] = "template_not_completed"
    _write(run / "response.json", response)
    with pytest.raises(LLMProtocolError, match="control"):
        verify_recorded_run(run)


@pytest.mark.parametrize(
    ("filename", "field", "value", "message"),
    [
        (
            "response.json",
            "finish_reason",
            "Bearer abcdefghijklmnopqrstuvwxyz",
            "credential",
        ),
        ("ground_truth.json", "source_locator", "person@example.org", "email"),
        (
            "ground_truth.json",
            "source_locator",
            "C:\\Users\\person\\private.txt",
            "absolute local path",
        ),
    ],
)
def test_secret_pii_and_local_path_are_rejected(
    tmp_path, filename, field, value, message
):
    run = _complete_bundle(tmp_path)
    record = _read(run / filename)
    if filename == "response.json":
        record["attempts"][0][field] = value
    else:
        record["provenance"][field] = value
    _write(run / filename, record)
    with pytest.raises(LLMProtocolError, match=message):
        verify_recorded_run(run)


def test_redaction_cannot_alter_decisions_or_candidate_spans(tmp_path):
    run = _complete_bundle(tmp_path)
    request = _read(run / "request.json")
    _write(
        run / "redaction_log.json",
        {
            "schema_version": 2,
            "run_id": request["run_id"],
            "evidence_class": "control",
            "status": "completed",
            "entries": [
                {
                    "artifact": "review.json",
                    "json_path": "$.decisions[0]",
                    "reason": "remove identity",
                    "original_sha256": "a" * 64,
                    "redacted_sha256": "b" * 64,
                    "affects_candidate_spans": False,
                }
            ],
        },
    )
    with pytest.raises(LLMProtocolError, match="may not alter review.json"):
        verify_recorded_run(run)


def test_failure_and_retry_attempts_must_both_be_preserved_in_timing(tmp_path):
    run = _complete_bundle(tmp_path)
    request = _read(run / "request.json")
    response = _read(run / "response.json")
    failed = copy.deepcopy(response["attempts"][0])
    failed.update(
        {
            "attempt_id": "A000",
            "status": "failure",
            "raw_response": "",
            "finish_reason": None,
            "usage": None,
            "failure": {
                "type": "transport_error",
                "message": "connection interrupted",
                "retryable": True,
            },
            "started_at": "2025-01-01T09:59:59+08:00",
            "completed_at": "2025-01-01T10:00:00+08:00",
        }
    )
    failed["request_sha256"] = _canonical_hash(request)
    response["attempts"].insert(0, failed)
    _write(run / "response.json", response)
    timing = _read(run / "timing.json")
    timing["attempts"].insert(
        0,
        {"attempt_id": "A000", "status": "failure", "duration_seconds": 1.0},
    )
    timing["stages_seconds"]["provider_interaction"] = 3.0
    timing["stage_intervals"]["provider_interaction"] = {
        "started_at": "2025-01-01T09:59:59+08:00",
        "completed_at": "2025-01-01T10:00:02+08:00",
        "duration_seconds": 3.0,
    }
    timing["total_seconds"] = 8.0
    _write(run / "timing.json", timing)
    evaluation = _read(run / "evaluation.json")
    evaluation["timing_seconds"]["provider_interaction"] = 3.0
    evaluation["timing_seconds"]["total"] = 8.0
    _write(run / "evaluation.json", evaluation)
    assert verify_recorded_run(run)["status"] == "pass"


def test_cli_fails_nonzero_without_modifying_invalid_evidence(tmp_path):
    run = _complete_bundle(tmp_path)
    parsed = _read(run / "parsed_candidates.json")
    parsed["candidates"][0]["source_trace"]["start_char"] = 0
    _write(run / "parsed_candidates.json", parsed)
    before = _snapshot(run)
    result = CliRunner().invoke(main, ["evaluate-llm-offline", str(run)])
    assert result.exit_code != 0
    assert "source trace does not match" in result.output
    assert _snapshot(run) == before


def test_recorded_subject_responses_are_complete_and_provider_free():
    responses = sorted(
        Path("experiment-data/llm/gpt5_session/subjects").glob("*/response.json")
    )
    assert len(responses) == 5
    payloads = [_read(path) for path in responses]
    assert all(payload["run_id"] == "gpt5" for payload in payloads)
    assert sum(len(payload["response"]["candidates"]) for payload in payloads) == 69

    def keys(value):
        if isinstance(value, dict):
            yield from value
            for child in value.values():
                yield from keys(child)
        elif isinstance(value, list):
            for child in value:
                yield from keys(child)

    all_keys = set().union(*(set(keys(payload)) for payload in payloads))
    assert "status" not in all_keys
    assert "independent_review_status" not in all_keys
