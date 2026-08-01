"""Deterministic implementation of MPSC Algorithm 1."""

from __future__ import annotations

from typing import Any

from ..config import MPSCConfig
from ..models import KillVector, MetamorphicRelation, MROptimizationResult
from ..mutation.mutation_score import compute_mutation_score
from .distance import compute_difference_score


def optimize_mr_category_with_trace(
    mrs: list[MetamorphicRelation],
    kill_vectors: dict[str, KillVector],
    config: MPSCConfig,
) -> dict[str, Any]:
    """Optimize one category and retain every deterministic decision."""

    _validate_inputs(mrs, kill_vectors, config)
    original = sorted(mr.mr_id for mr in mrs)
    retained = list(original)
    mutation_scores = {
        mr_id: compute_mutation_score(kill_vectors[mr_id]) for mr_id in original
    }
    iterations: list[dict[str, Any]] = []

    while len(retained) > config.min_set_size:
        difference_scores = {
            mr_id: compute_difference_score(
                mr_id,
                retained,
                kill_vectors,
            )
            for mr_id in retained
        }
        combined_scores = {
            mr_id: (
                config.ms_weight * mutation_scores[mr_id]
                + config.ds_weight * difference_scores[mr_id]
            )
            for mr_id in retained
        }
        weakest = min(
            retained,
            key=lambda mr_id: (combined_scores[mr_id], mr_id),
        )
        removed = combined_scores[weakest] < config.tau_c
        iterations.append(
            {
                "iteration": len(iterations) + 1,
                "retained_before": list(retained),
                "difference_scores": difference_scores,
                "combined_scores": combined_scores,
                "weakest_mr": weakest,
                "weakest_score": combined_scores[weakest],
                "threshold_tau_c": config.tau_c,
                "decision": "remove" if removed else "stop_threshold",
            }
        )
        if not removed:
            break
        retained.remove(weakest)

    stop_reason = (
        "min_set_size"
        if len(retained) <= config.min_set_size
        else "combined_score_threshold"
    )
    return {
        "original_mrs": original,
        "optimized_mrs": retained,
        "removed_mrs": [mr_id for mr_id in original if mr_id not in retained],
        "mutation_scores": mutation_scores,
        "iterations": iterations,
        "stop_reason": stop_reason,
        "parameters": {
            "tau_c": config.tau_c,
            "min_set_size": config.min_set_size,
            "ms_weight": config.ms_weight,
            "ds_weight": config.ds_weight,
        },
    }


def optimize_mr_category(
    mrs: list[MetamorphicRelation],
    kill_vectors: dict[str, KillVector],
    config: MPSCConfig,
) -> list[str]:
    """Algorithm 1 compatibility wrapper returning the optimized MR IDs."""

    return optimize_mr_category_with_trace(
        mrs,
        kill_vectors,
        config,
    )["optimized_mrs"]


def optimize_mr_set(
    mrs: list[MetamorphicRelation],
    kill_vectors: dict[str, KillVector],
    config: MPSCConfig,
) -> MROptimizationResult:
    """Apply Algorithm 1 independently to every MR category."""

    categories: dict[str, list[MetamorphicRelation]] = {}
    for mr in mrs:
        categories.setdefault(mr.category, []).append(mr)

    optimized_ids: list[str] = []
    mutation_scores: dict[str, float] = {}
    difference_scores: dict[str, float] = {}
    combined_scores: dict[str, float] = {}
    for category in sorted(categories):
        category_mrs = categories[category]
        trace = optimize_mr_category_with_trace(
            category_mrs,
            kill_vectors,
            config,
        )
        optimized_ids.extend(trace["optimized_mrs"])
        category_ids = sorted(mr.mr_id for mr in category_mrs)
        for mr_id in category_ids:
            ms = compute_mutation_score(kill_vectors[mr_id])
            ds = compute_difference_score(
                mr_id,
                category_ids,
                kill_vectors,
            )
            mutation_scores[mr_id] = ms
            difference_scores[mr_id] = ds
            combined_scores[mr_id] = config.ms_weight * ms + config.ds_weight * ds

    return MROptimizationResult(
        original_mrs=sorted(mr.mr_id for mr in mrs),
        optimized_mrs=optimized_ids,
        mutation_scores=mutation_scores,
        difference_scores=difference_scores,
        combined_scores=combined_scores,
    )


def _validate_inputs(
    mrs: list[MetamorphicRelation],
    kill_vectors: dict[str, KillVector],
    config: MPSCConfig,
) -> None:
    if config.tau_c is None:
        raise ValueError("tau_c is unknown and must be supplied explicitly")
    if not 0 <= config.tau_c <= 1:
        raise ValueError("tau_c must be between 0 and 1")
    if config.min_set_size is None:
        raise ValueError("min_set_size is unknown and must be supplied explicitly")
    if not 1 <= config.min_set_size <= len(mrs):
        raise ValueError("min_set_size must be between 1 and the category size")
    if config.ms_weight < 0 or config.ds_weight < 0:
        raise ValueError("score weights must be non-negative")
    if abs(config.ms_weight + config.ds_weight - 1.0) > 1e-12:
        raise ValueError("score weights must sum to 1")

    mr_ids = [mr.mr_id for mr in mrs]
    if len(set(mr_ids)) != len(mr_ids):
        raise ValueError("MR IDs must be unique within a category")
    missing = sorted(set(mr_ids) - set(kill_vectors))
    if missing:
        raise ValueError("missing complete kill vectors: " + ", ".join(missing))
    mutant_sets = {tuple(sorted(kill_vectors[mr_id].kills)) for mr_id in mr_ids}
    if len(mutant_sets) != 1 or not next(iter(mutant_sets), ()):
        raise ValueError("all kill vectors must contain the same non-empty mutant set")
