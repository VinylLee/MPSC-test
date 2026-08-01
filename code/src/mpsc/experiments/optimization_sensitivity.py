"""Sensitivity analysis for unknown reference parameters."""

from __future__ import annotations

import csv
import json
from itertools import product
from pathlib import Path
from typing import Any

import yaml

from ..config import MPSCConfig
from ..models import KillVector
from ..mr.optimizer import optimize_mr_category_with_trace
from .canonical_optimization import DEFAULT_SCORES, _relation

DEFAULT_SCAN_CONFIG = Path(
    "code/configs/experiments/mytoken_optimization_sensitivity.yaml"
)


def run_optimization_sensitivity(
    output_dir: str | Path,
    *,
    scores_path: str | Path = DEFAULT_SCORES,
    config_path: str | Path = DEFAULT_SCAN_CONFIG,
) -> dict[str, Any]:
    """Run and preserve every tau_c/minSetSize combination."""

    evidence = json.loads(Path(scores_path).read_text(encoding="utf-8"))
    scan = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    fixed = scan["fixed_parameters"]
    if fixed["tau"] != evidence["tau"]:
        raise ValueError("scan tau differs from score evidence tau")

    mr_ids = evidence["mr_ids"]
    mutant_ids = evidence["mutant_ids"]
    vectors = {
        mr_id: KillVector(
            mr_id,
            {
                mutant_id: bool(evidence["kill_vectors"][mr_id][mutant_id])
                for mutant_id in mutant_ids
            },
        )
        for mr_id in mr_ids
    }
    mrs = [_relation(mr_id) for mr_id in mr_ids]
    tau_values = scan["grid"]["tau_c"]
    size_values = scan["grid"]["min_set_size"]
    if not tau_values or not size_values:
        raise ValueError("sensitivity grid cannot be empty")

    scenarios = []
    for scenario_number, (tau_c, min_set_size) in enumerate(
        product(tau_values, size_values),
        start=1,
    ):
        config = MPSCConfig(
            tau=fixed["tau"],
            tau_c=float(tau_c),
            min_set_size=int(min_set_size),
            ms_weight=fixed["ms_weight"],
            ds_weight=fixed["ds_weight"],
        )
        trace = optimize_mr_category_with_trace(mrs, vectors, config)
        scenarios.append(
            {
                "scenario_id": f"S{scenario_number:02d}",
                "tau_c": float(tau_c),
                "min_set_size": int(min_set_size),
                "optimized_mrs": trace["optimized_mrs"],
                "removed_mrs": trace["removed_mrs"],
                "optimized_size": len(trace["optimized_mrs"]),
                "stop_reason": trace["stop_reason"],
                "iterations": trace["iterations"],
            }
        )

    outcomes: dict[tuple[str, ...], list[str]] = {}
    for scenario in scenarios:
        outcome = tuple(scenario["optimized_mrs"])
        outcomes.setdefault(outcome, []).append(scenario["scenario_id"])
    result = {
        "schema_version": 1,
        "experiment": "canonical_mytoken_parameter_sensitivity",
        "scan_id": scan["scan_id"],
        "claim_scope": scan["claim_scope"],
        "fixed_parameters": fixed,
        "scores_source": Path(scores_path).as_posix(),
        "config_source": Path(config_path).as_posix(),
        "grid": scan["grid"],
        "scenario_count": len(scenarios),
        "distinct_outcome_count": len(outcomes),
        "distinct_outcomes": [
            {
                "optimized_mrs": list(outcome),
                "scenario_ids": scenario_ids,
            }
            for outcome, scenario_ids in outcomes.items()
        ],
        "scenarios": scenarios,
    }
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    _write_json(output / "sensitivity.json", result)
    _write_csv(output / "sensitivity.csv", scenarios)
    _write_readme(output / "README.md", result)
    return result


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, scenarios: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "scenario_id",
                "tau_c",
                "min_set_size",
                "optimized_size",
                "optimized_mrs",
                "removed_mrs",
                "stop_reason",
            ]
        )
        for scenario in scenarios:
            writer.writerow(
                [
                    scenario["scenario_id"],
                    repr(scenario["tau_c"]),
                    scenario["min_set_size"],
                    scenario["optimized_size"],
                    ";".join(scenario["optimized_mrs"]),
                    ";".join(scenario["removed_mrs"]),
                    scenario["stop_reason"],
                ]
            )


def _write_readme(path: Path, result: dict[str, Any]) -> None:
    lines = [
        "# Canonical optimizer parameter sensitivity",
        "",
        "- Unknown parameters: `tau_c`, `minSetSize`",
        f"- Scenarios preserved: {result['scenario_count']}",
        f"- Distinct optimized sets: {result['distinct_outcome_count']}",
        f"- Claim scope: `{result['claim_scope']}`",
        "",
        "| Optimized set | Scenario count | Scenario IDs |",
        "| --- | ---: | --- |",
    ]
    for outcome in result["distinct_outcomes"]:
        lines.append(
            f"| {', '.join(outcome['optimized_mrs'])} | "
            f"{len(outcome['scenario_ids'])} | "
            f"{', '.join(outcome['scenario_ids'])} |"
        )
    lines.extend(
        [
            "",
            "All grid outcomes are retained. No parameter combination is "
            "selected or tuned to match a target outcome.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
