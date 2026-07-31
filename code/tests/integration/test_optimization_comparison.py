from mpsc.experiments.optimization_comparison import (
    write_optimization_comparison,
)


def test_comparison_is_scope_aware_and_never_tuned(tmp_path):
    report = tmp_path / "comparison.md"

    result = write_optimization_comparison(report)

    assert result["conclusion"] == "independent_engineering_comparison"
    assert result["tuning_performed"] is False
    assert result["supplied"]["mr_before"] == 38
    assert result["supplied"]["mr_after"] == 24
    assert result["canonical"]["mr_before"] == 3
    assert result["canonical"]["mr_after"] == 2
    assert result["sensitivity_scenarios_preserved"] == 30
    assert all(
        row["status"]
        in {
            "different_scope_not_numerically_comparable",
            "not_measured_canonical",
        }
        for row in result["comparisons"]
    )
    content = report.read_text(encoding="utf-8")
    assert "No tuning was performed" in content
    assert "independent engineering comparison" in content
