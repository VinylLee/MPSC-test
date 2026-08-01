"""Release gates for subject qualification and result lineage."""

from __future__ import annotations

import csv
import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest
from click.testing import CliRunner
from mpsc.cli import main
from mpsc.reporting import generate_computed_tables
from mpsc.results_evidence import (
    _validate_canonical_matrix,
    _validate_repetition_score_optimizer_chain,
    canonical_cell_detection,
    validate_results_evidence,
    validate_subject_manifest,
)

INDEX = Path("experiment-data/results/results_evidence_index.json")
SUBJECTS = Path("experiment-data/subjects/subject_manifest.json")


def _write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _validate(index: Path = INDEX, *, qualify: bool = False):
    return validate_results_evidence(
        index,
        subject_manifest_path=SUBJECTS,
        qualify_subjects=qualify,
    )


def _load_index() -> dict:
    return json.loads(INDEX.read_text(encoding="utf-8"))


def test_five_subject_manifest_is_bidirectional_and_hash_frozen():
    result = validate_subject_manifest(SUBJECTS)
    manifest = json.loads(SUBJECTS.read_text(encoding="utf-8"))

    assert result["status"] == "pass", result["errors"]
    assert result["subject_count"] == 5
    assert {row["evidence_class"] for row in manifest["subjects"]} == {"control"}
    assert {row["mr_binding_status"] for row in manifest["subjects"]} == {"verified"}


def test_all_five_subjects_fresh_compile_deploy_and_qualify():
    result = validate_subject_manifest(SUBJECTS, qualify=True)

    assert result["status"] == "pass", result["errors"]
    assert result["qualified_subject_count"] == 5


def test_results_index_hashes_dag_classes_and_dimensions_pass():
    index = _load_index()
    result = _validate()

    assert "claim_boundary" not in index
    assert all("claim_boundary" not in artifact for artifact in index["artifacts"])
    assert result["status"] == "pass", result["errors"]
    assert result["artifact_count"] == 10
    assert result["lineage_edge_count"] == 9
    assert result["processed_mapping_count"] == 14
    assert result["canonical_matrix_dimensions"] == {
        "mr_count": 3,
        "baseline_count": 1,
        "mutant_count": 3,
        "cell_count": 12,
    }


@pytest.mark.parametrize(
    "raw",
    [
        {"execution_status": "error", "oracle_verdict": "pass", "errors": ["boom"]},
        {"execution_status": "completed", "oracle_verdict": None, "errors": []},
        {
            "execution_status": "completed",
            "oracle_verdict": "pass",
            "errors": ["hidden"],
        },
        {
            "execution_status": "completed",
            "oracle_verdict": "pass",
            "errors": [],
            "required_predicates_complete": False,
        },
    ],
)
def test_error_and_none_cells_cannot_be_counted_as_survive(raw):
    with pytest.raises(ValueError, match="indeterminate"):
        canonical_cell_detection(raw)


def test_complete_pass_and_violation_cells_have_unambiguous_detection():
    assert (
        canonical_cell_detection(
            {
                "execution_status": "completed",
                "oracle_verdict": "pass",
                "errors": [],
                "required_predicates_complete": True,
            }
        )
        == 0
    )
    assert (
        canonical_cell_detection(
            {
                "execution_status": "completed",
                "oracle_verdict": "violation",
                "errors": [],
                "required_predicates_complete": True,
            }
        )
        == 1
    )


def test_artifact_reclassification_fails(tmp_path):
    index = _load_index()
    tampered = deepcopy(index)
    artifact = next(
        row
        for row in tampered["artifacts"]
        if row["artifact_id"] == "comparison_aggregates"
    )
    artifact["evidence_class"] = "control"
    path = tmp_path / "tampered-index.json"
    _write_json(path, tampered)

    result = _validate(path)
    assert result["status"] == "fail"
    assert any("cannot be reclassified" in error for error in result["errors"])


def test_lineage_cycle_and_hash_tamper_fail(tmp_path):
    index = _load_index()
    tampered = deepcopy(index)
    matrix = next(
        row
        for row in tampered["artifacts"]
        if row["artifact_id"] == "mytoken_canonical_matrix"
    )
    matrix["sha256_tree"] = "0" * 64
    matrix["upstream"] = ["mytoken_optimizer"]
    path = tmp_path / "tampered-index.json"
    _write_json(path, tampered)

    result = _validate(path)
    assert result["status"] == "fail"
    assert any("SHA-256 mismatch" in error for error in result["errors"])
    assert any("lineage cycle" in error for error in result["errors"])


def test_processed_mappings_reference_existing_bounded_files():
    index = _load_index()
    mappings = index["processed_output_mappings"]

    assert len(mappings) == 14
    assert all(Path(row["input"]).is_file() for row in mappings)
    assert all(Path(row["output"]).is_file() for row in mappings)
    assert all(row["boundary"] for row in mappings)


def test_cli_success_is_read_only_and_tamper_is_nonzero(tmp_path):
    before = INDEX.read_bytes()
    runner = CliRunner()
    success = runner.invoke(main, ["verify-results-evidence"])

    assert success.exit_code == 0, success.output
    assert '"status": "pass"' in success.output
    assert INDEX.read_bytes() == before

    index = _load_index()
    index["index_id"] = "tampered-index"
    tampered = tmp_path / "tampered-index.json"
    _write_json(tampered, index)
    failure = runner.invoke(
        main,
        ["verify-results-evidence", "--index", str(tampered)],
    )
    assert failure.exit_code != 0
    assert "index_id changed" in failure.output


def test_all_seven_computed_tables_regenerate_from_processed_inputs(tmp_path):
    output = tmp_path / "tables"
    result = generate_computed_tables(output_dir=output)

    assert result["table_count"] == 7
    for generated in result["tables"]:
        actual_path = Path(generated["path"])
        expected_path = Path("experiment-data/processed/computed") / actual_path.name
        with actual_path.open(encoding="utf-8-sig", newline="") as handle:
            actual = list(csv.DictReader(handle))
        with expected_path.open(encoding="utf-8-sig", newline="") as handle:
            expected = list(csv.DictReader(handle))
        assert actual == expected, actual_path.name


@pytest.mark.parametrize("mutation", ["missing_node", "extra_node", "extra_edge"])
def test_exact_artifact_node_and_edge_contract_rejects_drift(tmp_path, mutation):
    index = _load_index()
    if mutation == "missing_node":
        index["artifacts"].pop()
    elif mutation == "extra_node":
        extra = deepcopy(index["artifacts"][0])
        extra["artifact_id"] = "invented_result"
        index["artifacts"].append(extra)
    else:
        root = next(
            item
            for item in index["artifacts"]
            if item["artifact_id"] == "aggregate_results"
        )
        root["upstream"] = ["five_subject_qualification"]
    path = tmp_path / "tampered-index.json"
    _write_json(path, index)

    result = _validate(path)
    assert result["status"] == "fail"
    assert any(
        "frozen 10-node set" in error
        or "exactly 9 edges" in error
        or "upstream edge set changed" in error
        for error in result["errors"]
    )


@pytest.mark.parametrize("mutation", ["missing", "extra", "rewired"])
def test_exact_processed_mapping_contract_rejects_drift(tmp_path, mutation):
    index = _load_index()
    if mutation == "missing":
        index["processed_output_mappings"].pop()
    elif mutation == "extra":
        extra = deepcopy(index["processed_output_mappings"][0])
        extra["mapping_id"] = "table-invented"
        index["processed_output_mappings"].append(extra)
    else:
        index["processed_output_mappings"][0]["output"] = (
            "experiment-data/processed/computed/mutation_scores.csv"
        )
    path = tmp_path / "tampered-index.json"
    _write_json(path, index)

    result = _validate(path)
    assert result["status"] == "fail"
    assert any(
        "frozen 14-item set" in error or "input/output mapping changed" in error
        for error in result["errors"]
    )


def test_gnosis_cannot_acquire_a_write_claim_in_alternate_manifest(tmp_path):
    manifest = json.loads(SUBJECTS.read_text(encoding="utf-8"))
    gnosis = next(
        item for item in manifest["subjects"] if item["subject_id"] == "gnosissafeproxy"
    )
    gnosis["qualification"]["write_qualification_status"] = "executed"
    gnosis["qualification"]["steps"].append(
        {
            "id": "invented-write",
            "action": "transact",
            "function": "fallback",
            "arguments": [],
            "expect_success": True,
        }
    )
    path = tmp_path / "subjects.json"
    _write_json(path, manifest)

    result = validate_subject_manifest(path)
    assert result["status"] == "fail"
    assert any("write qualification" in error for error in result["errors"])
    assert any("only the selector observation" in error for error in result["errors"])


def test_canonical_predicate_completeness_tamper_fails(tmp_path):
    source = Path("experiment-data/results/canonical/mytoken_mr6_small")
    destination = (
        tmp_path / "experiment-data" / "results" / "canonical" / "mytoken_mr6_small"
    )
    shutil.copytree(source, destination)
    cell = destination / "cells" / "MR6.1" / "MUT-01.json"
    payload = json.loads(cell.read_text(encoding="utf-8"))
    payload["required_predicates_complete"] = False
    _write_json(cell, payload)

    errors = []
    _validate_canonical_matrix(tmp_path, errors)
    assert any("predicates incomplete" in error for error in errors)


@pytest.mark.parametrize("mutation", ["mrd", "trajectory", "parameters"])
def test_optimizer_computation_rejects_tampering(tmp_path, mutation):
    canonical_source = Path("experiment-data/results/canonical/mytoken_optimization")
    canonical_destination = (
        tmp_path / "experiment-data" / "results" / "canonical" / "mytoken_optimization"
    )
    shutil.copytree(canonical_source, canonical_destination)
    config_source = Path("code/configs/experiments/mytoken_canonical_optimization.yaml")
    config_destination = (
        tmp_path
        / "code"
        / "configs"
        / "experiments"
        / "mytoken_canonical_optimization.yaml"
    )
    config_destination.parent.mkdir(parents=True)
    shutil.copy2(config_source, config_destination)
    optimization_path = canonical_destination / "algorithm1" / "optimization.json"
    optimization = json.loads(optimization_path.read_text(encoding="utf-8"))
    if mutation == "mrd":
        optimization["pairwise_mrd"]["MR6.1"]["MR6.4"] = 0.25
    elif mutation == "trajectory":
        optimization["algorithm_1"]["iterations"][0]["decision"] = "keep"
    else:
        optimization["algorithm_1"]["parameters"]["tau_c"] = 0.9
    _write_json(optimization_path, optimization)

    errors = []
    _validate_repetition_score_optimizer_chain(tmp_path, errors)
    assert any("recompute" in error for error in errors)


def test_invalid_score_tau_is_reported_without_validator_traceback(tmp_path):
    canonical_source = Path("experiment-data/results/canonical/mytoken_optimization")
    canonical_destination = (
        tmp_path / "experiment-data" / "results" / "canonical" / "mytoken_optimization"
    )
    shutil.copytree(canonical_source, canonical_destination)
    config_source = Path("code/configs/experiments/mytoken_canonical_optimization.yaml")
    config_destination = (
        tmp_path
        / "code"
        / "configs"
        / "experiments"
        / "mytoken_canonical_optimization.yaml"
    )
    config_destination.parent.mkdir(parents=True)
    shutil.copy2(config_source, config_destination)
    score_path = canonical_destination / "scores" / "kill_vectors.json"
    score = json.loads(score_path.read_text(encoding="utf-8"))
    score["tau"] = "not-a-number"
    _write_json(score_path, score)

    errors = []
    _validate_repetition_score_optimizer_chain(tmp_path, errors)
    assert any("tau must be a number" in error for error in errors)
