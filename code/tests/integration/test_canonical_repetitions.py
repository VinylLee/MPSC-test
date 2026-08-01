import json

from mpsc.experiments.canonical_repetitions import (
    run_repeated_mytoken_matrix,
)


def test_repeated_matrix_records_eligible_stable_cells(tmp_path):
    output = tmp_path / "repeated"

    summary = run_repeated_mytoken_matrix(output, repetitions=2)

    assert summary["total_runs"] == 24
    assert summary["completed_runs"] == 24
    assert summary["error_runs"] == 0
    assert summary["complete_required_predicate_runs"] == 24
    assert len(summary["cells"]) == 9
    assert all(cell["TCE"] == 2 for cell in summary["cells"])
    assert all(cell["stable"] for cell in summary["cells"])
    assert {
        (cell["mr_id"], cell["mutant_id"]): cell["TCK"] for cell in summary["cells"]
    } == {
        ("MR6.1", "MUT-01"): 0,
        ("MR6.1", "MUT-07"): 0,
        ("MR6.1", "MUT-08"): 2,
        ("MR6.4", "MUT-01"): 0,
        ("MR6.4", "MUT-07"): 0,
        ("MR6.4", "MUT-08"): 0,
        ("MR6.6", "MUT-01"): 0,
        ("MR6.6", "MUT-07"): 0,
        ("MR6.6", "MUT-08"): 2,
    }

    evidence = json.loads(
        (output / "runs" / "MR6.1" / "MUT-08" / "run-01.json").read_text(
            encoding="utf-8"
        )
    )
    assert evidence["fresh_state_required"] is True
    assert evidence["execution_status"] == "completed"
    assert evidence["required_predicates_complete"] is True
    assert evidence["oracle_verdict"] == "violation"
    assert evidence["errors"] == []
    assert evidence["source_observation"] is not None
    assert evidence["followup_observation"] is not None
