"""Scope-aware comparison of canonical and supplied optimization results."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from ..models import KillVector
from ..mr.distance import compute_jaccard_distance

DEFAULT_SUPPLIED_METRICS = Path("experiment-data/processed/optimization_metrics.csv")
DEFAULT_ALGORITHM = Path(
    "experiment-data/results/canonical/mytoken_optimization/algorithm1/optimization.json"
)
DEFAULT_SENSITIVITY = Path(
    "experiment-data/results/canonical/mytoken_optimization/sensitivity/sensitivity.json"
)


def write_optimization_comparison(
    report_path: str | Path,
    *,
    json_path: str | Path | None = None,
    supplied_metrics_path: str | Path = DEFAULT_SUPPLIED_METRICS,
    algorithm_path: str | Path = DEFAULT_ALGORITHM,
    sensitivity_path: str | Path = DEFAULT_SENSITIVITY,
) -> dict[str, Any]:
    """Write a no-tuning comparison with explicit scope incompatibilities."""

    with Path(supplied_metrics_path).open(
        newline="",
        encoding="utf-8-sig",
    ) as handle:
        supplied = next(
            row for row in csv.DictReader(handle) if row["contract"] == "MyToken"
        )
    algorithm = _read_json(Path(algorithm_path))
    sensitivity = _read_json(Path(sensitivity_path))
    trace = algorithm["algorithm_1"]
    original = trace["original_mrs"]
    optimized = trace["optimized_mrs"]
    scores = trace["mutation_scores"]
    vectors = {
        mr_id: KillVector(
            mr_id,
            {
                mutant_id: bool(value)
                for mutant_id, value in algorithm["kill_vectors"][mr_id].items()
            },
        )
        for mr_id in original
    }

    canonical = {
        "scenario_id": algorithm["scenario_id"],
        "claim_scope": algorithm["claim_scope"],
        "mr_before": len(original),
        "mr_after": len(optimized),
        "mr_reduction_percent": _reduction(len(original), len(optimized)),
        "average_mrd_before": _average_pairwise_mrd(original, vectors),
        "average_mrd_after": _average_pairwise_mrd(optimized, vectors),
        "average_mutation_score_before": _average(
            [scores[mr_id] for mr_id in original]
        ),
        "average_mutation_score_after": _average(
            [scores[mr_id] for mr_id in optimized]
        ),
        "time_before_seconds": None,
        "time_after_seconds": None,
        "vulnerabilities_before": None,
        "vulnerabilities_after": None,
    }
    supplied = {
        "scope": "supplied_office_comparison",
        "mr_before": int(supplied["mr_before"]),
        "mr_after": int(supplied["mr_after"]),
        "mr_reduction_percent": _reduction(
            int(supplied["mr_before"]),
            int(supplied["mr_after"]),
        ),
        "average_mrd_before": float(supplied["mrd_before"]),
        "average_mrd_after": float(supplied["mrd_after"]),
        "average_mutation_score_before": float(supplied["mutation_score_before"]),
        "average_mutation_score_after": float(supplied["mutation_score_after"]),
        "time_before_seconds": float(supplied["time_before_seconds"]),
        "time_after_seconds": float(supplied["time_after_seconds"]),
        "vulnerabilities_before": int(supplied["office_vulnerabilities_before"]),
        "vulnerabilities_after": int(supplied["office_vulnerabilities_after"]),
        "source_file": supplied["source_path"],
        "source_locator": supplied["source_locator"],
    }
    comparisons = [
        _comparison(
            metric,
            supplied[metric],
            canonical[metric],
            (
                "different_scope_not_numerically_comparable"
                if canonical[metric] is not None
                else "not_measured_canonical"
            ),
        )
        for metric in (
            "mr_before",
            "mr_after",
            "mr_reduction_percent",
            "average_mrd_before",
            "average_mrd_after",
            "average_mutation_score_before",
            "average_mutation_score_after",
            "time_before_seconds",
            "time_after_seconds",
            "vulnerabilities_before",
            "vulnerabilities_after",
        )
    ]
    result = {
        "schema_version": 1,
        "experiment": "canonical_vs_supplied_mytoken_optimization",
        "conclusion": "independent_engineering_comparison",
        "tuning_performed": False,
        "scope_differences": {
            "supplied": "38 MRs and the supplied MuSC mutant set",
            "canonical": (
                "3 executable MR6 relations and 3 engineering-control mutants"
            ),
        },
        "supplied": supplied,
        "canonical": canonical,
        "sensitivity_scenarios_preserved": sensitivity["scenario_count"],
        "sensitivity_distinct_outcomes": sensitivity["distinct_outcome_count"],
        "comparisons": comparisons,
    }
    report = Path(report_path)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(_markdown(result), encoding="utf-8")
    destination = (
        Path(json_path) if json_path is not None else report.with_suffix(".json")
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def _comparison(
    metric: str,
    supplied_value: float | int,
    canonical_value: float | int | None,
    status: str,
) -> dict[str, Any]:
    return {
        "metric": metric,
        "supplied_value": supplied_value,
        "canonical_value": canonical_value,
        "status": status,
    }


def _average_pairwise_mrd(
    mr_ids: list[str],
    vectors: dict[str, KillVector],
) -> float:
    distances = [
        compute_jaccard_distance(vectors[left], vectors[right])
        for index, left in enumerate(mr_ids)
        for right in mr_ids[index + 1 :]
    ]
    return _average(distances)


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _reduction(before: int, after: int) -> float:
    return (before - after) / before * 100


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _format(value: Any) -> str:
    if value is None:
        return "not measured"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _markdown(result: dict[str, Any]) -> str:
    supplied = result["supplied"]
    canonical = result["canonical"]
    lines = [
        "# Canonical MyToken optimization vs supplied result",
        "",
        "## Conclusion",
        "",
        "**Classification: independent engineering comparison.** The two "
        "columns use different MR and mutant universes, and `tau_c` and "
        "`minSetSize` are not reported. No tuning was performed.",
        "",
        "## Scope",
        "",
        f"- Supplied: {result['scope_differences']['supplied']}.",
        f"- Canonical: {result['scope_differences']['canonical']}.",
        f"- Canonical scenario: `{canonical['scenario_id']}`.",
        f"- Sensitivity: {result['sensitivity_scenarios_preserved']} "
        "scenarios and "
        f"{result['sensitivity_distinct_outcomes']} distinct outcomes "
        "preserved.",
        "",
        "## Side-by-side values",
        "",
        "| Metric | Supplied | Canonical | Status |",
        "| --- | ---: | ---: | --- |",
    ]
    for row in result["comparisons"]:
        lines.append(
            f"| {row['metric']} | {_format(row['supplied_value'])} | "
            f"{_format(row['canonical_value'])} | `{row['status']}` |"
        )
    lines.extend(
        [
            "",
            "## Provenance",
            "",
            f"- Supplied Excel values: `{supplied['source_file']}`, "
            f"`{supplied['source_locator']}`.",
            "- Canonical values: "
            "`experiment-data/results/canonical/mytoken_optimization/algorithm1/`.",
            "- Parameter outcomes: "
            "`experiment-data/results/canonical/mytoken_optimization/sensitivity/`.",
            "",
            "The report intentionally does not identify a closest scenario "
            "or change the mutant/MR set to improve numeric agreement.",
            "",
        ]
    )
    return "\n".join(lines)
