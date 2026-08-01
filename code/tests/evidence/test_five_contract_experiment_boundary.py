"""Freeze the evidence boundary for the five-contract experiment."""

import csv
import json
import subprocess
from pathlib import Path

SUBJECTS = Path("experiment-data/subjects/subject_manifest.json")
CORPUS = Path("experiment-data/mutants/corpus_manifest.json")


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_dependency_closure_matches_underlying_gap_records():
    subjects = _load(SUBJECTS)
    corpus = _load(CORPUS)

    assert len(subjects["subjects"]) == 5
    assert {row["name"] for row in subjects["subjects"]} == set(
        corpus["subject_counts"]
    )
    assert corpus["total_mutants"] == 535
    assert corpus["total_non_equivalent"] == 495


def test_supplied_mutation_scores_recompute_but_are_not_independent_results():
    with Path("experiment-data/processed/mutation_scores.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 15
    valid_by_contract = {row["contract"]: int(row["valid_mutants"]) for row in rows}
    assert sum(valid_by_contract.values()) == 495
    assert all(
        round(100 * int(row["killed_mutants"]) / int(row["valid_mutants"]), 6)
        == float(row["mutation_score_percent"])
        for row in rows
    )


def test_optimization_layer_preserves_missing_inputs_and_discrepancies():
    with Path("experiment-data/processed/optimization_metrics.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 5
    assert sum(int(row["mr_before"]) for row in rows) == 302
    assert sum(int(row["mr_after"]) for row in rows) == 173
    assert all(float(row["time_after_seconds"]) > 0 for row in rows)


def test_timing_is_a_four_row_summary_without_provenance():
    with Path("experiment-data/processed/method_time_comparison.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))

    observed = {row["method"]: float(row["total_time_seconds"]) for row in rows}
    assert len(rows) == 4
    assert set(observed) == {"MPSC", "VDMBSCMT", "Solhint", "Slither"}
    assert all(value > 0 for value in observed.values())


def test_engineering_and_outputs_are_explicitly_prohibited():
    tracked = subprocess.check_output(
        ["git", "ls-files"], text=True, encoding="utf-8"
    ).splitlines()
    assert not [path for path in tracked if path.startswith("outputs/")]
    assert not [path for path in tracked if path.startswith("experiment-data/runs/")]
    assert Path("experiment-data/results/canonical").is_dir()
