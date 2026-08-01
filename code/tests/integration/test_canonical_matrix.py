"""End-to-end evidence test for the canonical 2 x 3 matrix."""

import csv
import json

import mpsc.experiments.canonical_matrix as canonical_matrix
from mpsc.experiments.canonical_matrix import run_canonical_mytoken_matrix
from mpsc.solidity.compiler import CompileResult


def test_canonical_small_matrix_contains_real_evidence(tmp_path):
    output = tmp_path / "canonical"

    summary = run_canonical_mytoken_matrix(output)

    assert summary["total_cells"] == 12
    assert summary["completed_cells"] == 12
    assert summary["baseline"] == {
        "MR6.1": "pass",
        "MR6.4": "pass",
        "MR6.6": "pass",
    }
    assert summary["baseline_eligible"] is True
    assert summary["killed_mutants"] == ["MUT-08"]
    assert summary["surviving_mutants"] == ["MUT-01", "MUT-07"]
    assert summary["indeterminate_mutants"] == []
    with (output / "detection_matrix.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [
        {
            "mr_id": "MR6.1",
            "MUT-01": "0",
            "MUT-07": "0",
            "MUT-08": "1",
        },
        {
            "mr_id": "MR6.4",
            "MUT-01": "0",
            "MUT-07": "0",
            "MUT-08": "0",
        },
        {
            "mr_id": "MR6.6",
            "MUT-01": "0",
            "MUT-07": "0",
            "MUT-08": "1",
        },
    ]

    cell = json.loads(
        (output / "cells" / "MR6.1" / "MUT-08.json").read_text(encoding="utf-8")
    )
    assert cell["execution_status"] == "completed"
    assert cell["oracle_verdict"] == "violation"
    assert cell["source_observation"] is not None
    assert cell["followup_observation"] is not None
    assert cell["oracle_result"]["predicate_components"]


def test_error_cell_is_indeterminate_and_never_counted_as_surviving(
    tmp_path, monkeypatch
):
    real_compile = canonical_matrix.compile_contract_solcx
    error_path = canonical_matrix.DEFAULT_SUBJECTS["MUT-01"]

    def fail_one_subject(path, compiler_version):
        if path == error_path:
            return CompileResult(
                contract_name="MyToken",
                compiler_version=compiler_version,
                success=False,
                errors=["synthetic compile failure"],
            )
        return real_compile(path, compiler_version)

    monkeypatch.setattr(
        canonical_matrix,
        "compile_contract_solcx",
        fail_one_subject,
    )
    summary = run_canonical_mytoken_matrix(
        tmp_path / "canonical",
        subjects={
            "original": canonical_matrix.DEFAULT_SUBJECTS["original"],
            "ERROR": error_path,
        },
        mr_ids=("MR6.1",),
    )

    assert summary["killed_mutants"] == []
    assert summary["surviving_mutants"] == []
    assert summary["indeterminate_mutants"] == ["ERROR"]
    assert summary["completed_cells"] == 1


def test_baseline_error_makes_otherwise_passing_mutant_indeterminate(
    tmp_path, monkeypatch
):
    real_compile = canonical_matrix.compile_contract_solcx
    baseline_path = canonical_matrix.DEFAULT_SUBJECTS["original"]

    def fail_baseline(path, compiler_version):
        if path == baseline_path:
            return CompileResult(
                contract_name="MyToken",
                compiler_version=compiler_version,
                success=False,
                errors=["synthetic baseline compile failure"],
            )
        return real_compile(path, compiler_version)

    monkeypatch.setattr(
        canonical_matrix,
        "compile_contract_solcx",
        fail_baseline,
    )
    summary = run_canonical_mytoken_matrix(
        tmp_path / "canonical",
        subjects={
            "original": baseline_path,
            "MUT-01": canonical_matrix.DEFAULT_SUBJECTS["MUT-01"],
        },
        mr_ids=("MR6.1",),
    )

    assert summary["baseline_eligible"] is False
    assert summary["killed_mutants"] == []
    assert summary["surviving_mutants"] == []
    assert summary["indeterminate_mutants"] == ["MUT-01"]
