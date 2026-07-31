from mpsc.experiments.optimization_sensitivity import (
    run_optimization_sensitivity,
)


def test_sensitivity_preserves_all_unknown_parameter_outcomes(tmp_path):
    result = run_optimization_sensitivity(tmp_path)

    assert result["scenario_count"] == 30
    assert result["distinct_outcome_count"] == 3
    assert {
        tuple(outcome["optimized_mrs"]) for outcome in result["distinct_outcomes"]
    } == {
        ("MR6.1", "MR6.4", "MR6.6"),
        ("MR6.4", "MR6.6"),
        ("MR6.6",),
    }
    scenarios = {
        (row["tau_c"], row["min_set_size"]): row for row in result["scenarios"]
    }
    assert scenarios[(0.4166666666666666, 1)]["removed_mrs"] == []
    assert scenarios[(0.4166666666666667, 1)]["removed_mrs"] == ["MR6.1"]
    assert scenarios[(0.5000000000000001, 1)]["optimized_mrs"] == ["MR6.6"]
