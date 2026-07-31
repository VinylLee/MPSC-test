import json
from copy import deepcopy
from pathlib import Path

import pytest
from mpsc.mutation import corpus
from mpsc.mutation.corpus import qualify_public_corpus, validate_public_corpus

MANIFEST = Path("experiment-data/mutants/corpus_manifest.json")


def _payload():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _validate_modified(tmp_path, payload):
    path = tmp_path / "corpus_manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return validate_public_corpus(path)


def test_manifest_and_disk_are_bidirectionally_complete():
    result = validate_public_corpus()

    assert result["status"] == "pass"
    assert result["declared_total"] == result["disk_total"] == 535
    assert result["subject_counts"] == {
        "MyToken": 53,
        "BecToken": 151,
        "PERSONAL_BANK": 83,
        "Rubixi": 172,
        "GnosisSafeProxy": 76,
    }
    assert result["equivalent_counts"] == {
        "MyToken": 4,
        "BecToken": 9,
        "PERSONAL_BANK": 2,
        "Rubixi": 19,
        "GnosisSafeProxy": 6,
    }


def test_hash_tamper_is_rejected(tmp_path):
    payload = _payload()
    payload["mutants"][0]["mutant"]["sha256"] = "0" * 64

    result = _validate_modified(tmp_path, payload)

    assert result["status"] == "fail"
    assert any("mutant.sha256 does not match" in error for error in result["errors"])


@pytest.mark.parametrize("duplicate_field", ["record_id", "mutant_id", "path"])
def test_duplicate_identity_or_path_is_rejected(tmp_path, duplicate_field):
    payload = _payload()
    if duplicate_field == "path":
        payload["mutants"][1]["mutant"]["path"] = payload["mutants"][0]["mutant"][
            "path"
        ]
        payload["mutants"][1]["mutant"]["sha256"] = payload["mutants"][0]["mutant"][
            "sha256"
        ]
    else:
        payload["mutants"][1][duplicate_field] = payload["mutants"][0][duplicate_field]

    result = _validate_modified(tmp_path, payload)

    assert result["status"] == "fail"
    assert any("duplicate" in error for error in result["errors"])


def test_count_mismatch_is_rejected(tmp_path):
    payload = _payload()
    payload["subject_counts"]["GnosisSafeProxy"] = 1

    result = _validate_modified(tmp_path, payload)

    assert result["status"] == "fail"
    assert any("subject_counts mismatch" in error for error in result["errors"])


def test_canonical_subset_is_exact_and_not_inferred(tmp_path):
    payload = _payload()
    payload["canonical_subset"]["record_ids"].append("MyToken::MUT-02")

    result = _validate_modified(tmp_path, payload)

    assert result["status"] == "fail"
    assert any(
        "canonical_subset must contain exactly" in error for error in result["errors"]
    )


def test_equivalent_count_mismatch_is_rejected(tmp_path):
    payload = _payload()
    payload["equivalent_counts"]["MyToken"] = 5

    result = _validate_modified(tmp_path, payload)

    assert result["status"] == "fail"
    assert any("equivalent_counts" in error for error in result["errors"])


@pytest.mark.parametrize(
    ("mutate", "expected_error"),
    [
        (
            lambda payload: payload.__setitem__("evidence_class", "control"),
            "evidence_class is not supported",
        ),
        (
            lambda payload: payload.__setitem__("claim_boundary", "legacy"),
            "claim_boundary is not supported",
        ),
        (
            lambda payload: payload["mutants"][0].__setitem__(
                "evidence_class", "control"
            ),
            "mutants[0].evidence_class is not supported",
        ),
        (
            lambda payload: payload["mutants"][0]["mutation"].__setitem__(
                "operator_basis", "textual_change"
            ),
            "operator_basis must use record_defaults",
        ),
        (
            lambda payload: payload["mutants"][0]["provenance"].__setitem__(
                "method", "documented_process"
            ),
            "provenance.method must use record_defaults",
        ),
        (
            lambda payload: payload["mutants"][0]["qualification"][
                "equivalence"
            ].__setitem__("rationale", "legacy"),
            "equivalence.rationale is not supported",
        ),
        (
            lambda payload: payload["canonical_subset"].__setitem__(
                "evidence_class", "control"
            ),
            "canonical_subset.evidence_class is not supported",
        ),
    ],
)
def test_removed_or_deduplicated_fields_are_rejected(
    tmp_path,
    mutate,
    expected_error,
):
    payload = _payload()
    mutate(payload)

    result = _validate_modified(tmp_path, payload)

    assert result["status"] == "fail"
    assert any(expected_error in error for error in result["errors"])


def test_qualification_mismatch_fails_closed(monkeypatch):
    payload = _payload()
    first_id = payload["mutants"][0]["record_id"]

    def fake_qualify(record, _base):
        failed = record["record_id"] == first_id
        return {
            "record_id": record["record_id"],
            "compiler_version": record["qualification"]["compile"]["compiler_version"],
            "compile_status": "verified_fail" if failed else "verified_pass",
            "compile_errors": ["sentinel"] if failed else [],
            "deploy_status": "not_verified" if failed else "verified_pass",
            "deployment_backend": "test",
        }

    monkeypatch.setattr(corpus, "_qualify_public_mutant", fake_qualify)

    result = qualify_public_corpus()

    assert result["status"] == "fail"
    assert result["qualified_count"] == 534
    assert any(first_id in error for error in result["errors"])


def test_per_file_source_record_cannot_disagree(tmp_path):
    payload = deepcopy(_payload())
    payload["mutants"][0]["provenance"]["source_record"] = payload["mutants"][1][
        "provenance"
    ]["source_record"]

    result = _validate_modified(tmp_path, payload)

    assert result["status"] == "fail"
    assert any("source_record" in error for error in result["errors"])


@pytest.mark.parametrize(
    ("field", "changed", "expected_error"),
    [
        ("operator", "UNVERIFIED", "source_record.operator"),
        ("line", 9999, "exceeds source line count"),
        ("line", 0, "line must be a positive integer"),
        ("original_text", "invented original", "original_text is not present"),
        ("mutated_text", "invented mutant", "mutated_text is not present"),
    ],
)
def test_mutation_metadata_tamper_is_rejected(
    tmp_path,
    field,
    changed,
    expected_error,
):
    payload = _payload()
    payload["mutants"][0]["mutation"][field] = changed

    result = _validate_modified(tmp_path, payload)

    assert result["status"] == "fail"
    assert any(expected_error in error for error in result["errors"])


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("compile", "compiler_version"),
        ("deploy", "backend"),
    ],
)
def test_qualification_metadata_is_required(tmp_path, section, field):
    payload = _payload()
    del payload["mutants"][0]["qualification"][section][field]

    result = _validate_modified(tmp_path, payload)

    assert result["status"] == "fail"
    assert any(
        f"qualification.{section}.{field}" in error for error in result["errors"]
    )


@pytest.mark.parametrize(
    ("compile_status", "deploy_status", "stillborn_status", "expected_error"),
    [
        (
            "verified_pass",
            "verified_pass",
            "unknown",
            "stillborn.status must be 'false'",
        ),
        (
            "verified_fail",
            "verified_pass",
            "false",
            "deploy cannot pass after compile failure",
        ),
        (
            "not_verified",
            "not_verified",
            "true",
            "stillborn.status must be 'false'",
        ),
    ],
)
def test_qualification_statuses_cannot_contradict_stillborn(
    tmp_path,
    compile_status,
    deploy_status,
    stillborn_status,
    expected_error,
):
    payload = _payload()
    qualification = payload["mutants"][0]["qualification"]
    qualification["compile"]["status"] = compile_status
    qualification["deploy"]["status"] = deploy_status
    qualification["stillborn"]["status"] = stillborn_status

    result = _validate_modified(tmp_path, payload)

    assert result["status"] == "fail"
    assert any(expected_error in error for error in result["errors"])


@pytest.mark.parametrize(
    ("mutate", "expected_error"),
    [
        (
            lambda payload: payload.__setitem__("corpus_id", "invalid-corpus"),
            "corpus_id",
        ),
        (
            lambda payload: payload["record_defaults"]["provenance"].__setitem__(
                "method", "specific_internal_method"
            ),
            "record_defaults",
        ),
        (
            lambda payload: payload.__setitem__(
                "schema_documentation", "missing-schema.md"
            ),
            "schema_documentation",
        ),
        (
            lambda payload: payload["qualification_environment"].__setitem__(
                "compile_command", "trust stored flags"
            ),
            "qualification_environment.compile_command",
        ),
        (
            lambda payload: payload["qualification_environment"].__setitem__(
                "py_solc_x", "unknown"
            ),
            "qualification_environment.py_solc_x",
        ),
    ],
)
def test_top_level_boundary_and_schema_tamper_is_rejected(
    tmp_path,
    mutate,
    expected_error,
):
    payload = _payload()
    mutate(payload)

    result = _validate_modified(tmp_path, payload)

    assert result["status"] == "fail"
    assert any(expected_error in error for error in result["errors"])
