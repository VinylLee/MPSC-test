"""Canonical MRD, combined scores, and Algorithm 1 evidence."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import yaml

from ..config import MPSCConfig
from ..models import (
    InputRelation,
    KillVector,
    MetamorphicRelation,
    OutputRelation,
)
from ..mr.distance import compute_difference_score, compute_jaccard_distance
from ..mr.optimizer import optimize_mr_category_with_trace

DEFAULT_SCORES = Path(
    "experiment-data/results/canonical/mytoken_optimization/scores/kill_vectors.json"
)
DEFAULT_CONFIG = Path("code/configs/experiments/mytoken_canonical_optimization.yaml")


def run_canonical_optimization(
    output_dir: str | Path,
    *,
    scores_path: str | Path = DEFAULT_SCORES,
    config_path: str | Path = DEFAULT_CONFIG,
) -> dict[str, Any]:
    """Compute Eq.4-Eq.6 and run deterministic Algorithm 1."""

    score_evidence = _read_json(Path(scores_path))
    scenario = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    parameters = scenario["parameters"]
    if parameters["tau"] != score_evidence["tau"]:
        raise ValueError("optimization tau differs from score evidence tau")

    mr_ids = score_evidence["mr_ids"]
    mutant_ids = score_evidence["mutant_ids"]
    kill_vectors = {
        mr_id: KillVector(
            mr_id=mr_id,
            kills={
                mutant_id: bool(score_evidence["kill_vectors"][mr_id][mutant_id])
                for mutant_id in mutant_ids
            },
        )
        for mr_id in mr_ids
    }
    mrs = [_relation(mr_id) for mr_id in reversed(mr_ids)]
    config = MPSCConfig(
        tau=parameters["tau"],
        tau_c=parameters["tau_c"],
        min_set_size=parameters["min_set_size"],
        ms_weight=parameters["ms_weight"],
        ds_weight=parameters["ds_weight"],
    )

    pairwise_mrd = {
        left: {
            right: compute_jaccard_distance(
                kill_vectors[left],
                kill_vectors[right],
            )
            for right in mr_ids
        }
        for left in mr_ids
    }
    initial_difference_scores = {
        mr_id: compute_difference_score(
            mr_id,
            mr_ids,
            kill_vectors,
        )
        for mr_id in mr_ids
    }
    trace = optimize_mr_category_with_trace(mrs, kill_vectors, config)
    initial_combined_scores = {
        mr_id: (
            config.ms_weight * trace["mutation_scores"][mr_id]
            + config.ds_weight * initial_difference_scores[mr_id]
        )
        for mr_id in mr_ids
    }
    result = {
        "schema_version": 1,
        "experiment": "canonical_mytoken_algorithm_1",
        "scenario_id": scenario["scenario_id"],
        "claim_scope": scenario["claim_scope"],
        "scores_source": Path(scores_path).as_posix(),
        "config_source": Path(config_path).as_posix(),
        "mr_ids": mr_ids,
        "mutant_ids": mutant_ids,
        "kill_vectors": score_evidence["kill_vectors"],
        "pairwise_mrd": pairwise_mrd,
        "initial_difference_scores": initial_difference_scores,
        "initial_combined_scores": initial_combined_scores,
        "algorithm_1": trace,
    }
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    _write_json(output / "optimization.json", result)
    _write_scores(output / "scores.csv", result)
    _write_readme(output / "README.md", result)
    return result


def _relation(mr_id: str) -> MetamorphicRelation:
    return MetamorphicRelation(
        mr_id=mr_id,
        category="MR6.amount_transform",
        target_operation="sendCoin",
        input_relation=InputRelation(
            description="canonical amount transformation",
            transform=mr_id,
        ),
        output_relation=OutputRelation(
            description="mr6_amount",
            check_type="mr6_amount",
        ),
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_scores(path: Path, result: dict[str, Any]) -> None:
    trace = result["algorithm_1"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "mr_id",
                "mutation_score",
                "difference_score",
                "combined_score",
                "retained",
            ]
        )
        for mr_id in result["mr_ids"]:
            writer.writerow(
                [
                    mr_id,
                    f"{trace['mutation_scores'][mr_id]:.12g}",
                    f"{result['initial_difference_scores'][mr_id]:.12g}",
                    f"{result['initial_combined_scores'][mr_id]:.12g}",
                    str(mr_id in trace["optimized_mrs"]).lower(),
                ]
            )


def _write_readme(path: Path, result: dict[str, Any]) -> None:
    trace = result["algorithm_1"]
    parameters = trace["parameters"]
    lines = [
        "# Canonical MyToken Algorithm 1 result",
        "",
        f"- Scenario: `{result['scenario_id']}`",
        f"- Claim scope: `{result['claim_scope']}`",
        f"- tau_c: {parameters['tau_c']} (not reported)",
        f"- minSetSize: {parameters['min_set_size']} (not reported)",
        f"- Original: {', '.join(trace['original_mrs'])}",
        f"- Optimized: {', '.join(trace['optimized_mrs'])}",
        f"- Removed: {', '.join(trace['removed_mrs']) or 'none'}",
        f"- Stop reason: {trace['stop_reason']}",
        "",
        "| MR | MS | DifferenceScore | CombinedScore |",
        "| --- | ---: | ---: | ---: |",
    ]
    for mr_id in result["mr_ids"]:
        lines.append(
            f"| {mr_id} | {trace['mutation_scores'][mr_id]:.6f} | "
            f"{result['initial_difference_scores'][mr_id]:.6f} | "
            f"{result['initial_combined_scores'][mr_id]:.6f} |"
        )
    lines.extend(
        [
            "",
            "This is one explicitly labeled demonstration scenario. "
            "It is not presented as a reference parameter setting.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
