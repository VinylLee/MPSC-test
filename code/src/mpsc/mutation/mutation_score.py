"""Mutation score computation for MPSC"""

from __future__ import annotations

from ..models import KillVector


def compute_kill_vector(
    mr_id: str,
    mutant_ids: list[str],
    detection_counts: dict[str, int],
    total_executions: dict[str, int],
    tau: float = 0.1,
) -> KillVector:
    """
    Compute kill vector K_i for an MR (Eq. 2 in TeX)

    K_ik = 1 if TCK_ik/TCE_ik >= tau else 0
    """
    if not 0 <= tau <= 1:
        raise ValueError("tau must be between 0 and 1")
    missing_counts = sorted(set(mutant_ids) - set(detection_counts))
    missing_totals = sorted(set(mutant_ids) - set(total_executions))
    if missing_counts or missing_totals:
        raise ValueError(
            "incomplete cell counts: "
            f"missing TCK={missing_counts}, missing TCE={missing_totals}"
        )

    kills: dict[str, bool] = {}
    for mutant_id in mutant_ids:
        tck = detection_counts[mutant_id]
        tce = total_executions[mutant_id]
        if tce <= 0 or tck < 0 or tck > tce:
            raise ValueError(f"invalid counts for {mutant_id}: TCK={tck}, TCE={tce}")
        ratio = tck / tce
        kills[mutant_id] = ratio >= tau

    return KillVector(mr_id=mr_id, kills=kills)


def compute_mutation_score(kill_vector: KillVector) -> float:
    """
    Compute mutation score MS_i (Eq. 3 in TeX)

    MS_i = (1/n) × Σ K_ik
    """
    if not kill_vector.kills:
        return 0.0

    n = len(kill_vector.kills)
    killed = sum(1 for v in kill_vector.kills.values() if v)

    return killed / n


def compute_average_mutation_score(mutation_scores: list[float]) -> float:
    """
    Compute average mutation score for an MR set (Eq. 7 in TeX)

    MS_avg = (1/|MRS|) × Σ MS_i
    """
    if not mutation_scores:
        return 0.0

    return sum(mutation_scores) / len(mutation_scores)
