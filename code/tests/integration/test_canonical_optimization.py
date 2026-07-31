import pytest
from mpsc.experiments.canonical_optimization import (
    run_canonical_optimization,
)


def test_canonical_optimization_has_expected_scores_and_trace(tmp_path):
    result = run_canonical_optimization(tmp_path)

    assert result["pairwise_mrd"]["MR6.1"] == {
        "MR6.1": 0.0,
        "MR6.4": 1.0,
        "MR6.6": 0.0,
    }
    assert result["initial_difference_scores"] == {
        "MR6.1": 0.5,
        "MR6.4": 1.0,
        "MR6.6": 0.5,
    }
    assert result["initial_combined_scores"] == {
        "MR6.1": pytest.approx(5 / 12),
        "MR6.4": 0.5,
        "MR6.6": pytest.approx(5 / 12),
    }
    trace = result["algorithm_1"]
    assert trace["original_mrs"] == ["MR6.1", "MR6.4", "MR6.6"]
    assert trace["optimized_mrs"] == ["MR6.4", "MR6.6"]
    assert trace["removed_mrs"] == ["MR6.1"]
    assert trace["iterations"][0]["weakest_mr"] == "MR6.1"
    assert trace["iterations"][0]["decision"] == "remove"
    assert trace["stop_reason"] == "min_set_size"
