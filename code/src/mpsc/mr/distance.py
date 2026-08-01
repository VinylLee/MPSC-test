"""MR distance module for MPSC - implements MRD (Jaccard distance)"""

from __future__ import annotations

from ..models import KillVector


def compute_jaccard_distance(ki: KillVector, kj: KillVector) -> float:
    """
    Compute MRD_ij using Jaccard distance (Eq. 4 in TeX)

    MRD_ij = 1 - [Σ min(K_ik, K_jk)] / [Σ max(K_ik, K_jk)]
    """
    all_mutants = set(ki.kills) | set(kj.kills)

    if not all_mutants:
        return 0.0

    numerator = 0
    denominator = 0

    for mutant_id in all_mutants:
        ki_val = 1 if ki.kills.get(mutant_id, False) else 0
        kj_val = 1 if kj.kills.get(mutant_id, False) else 0

        numerator += min(ki_val, kj_val)
        denominator += max(ki_val, kj_val)

    if denominator == 0:
        return 0.0

    return 1.0 - (numerator / denominator)


def compute_difference_score(
    mr_id: str,
    category_mrs: list[str],
    kill_vectors: dict[str, KillVector],
) -> float:
    """
    Compute DifferenceScore_i (Eq. 5 in TeX)

    DifferenceScore_i = (1/(|C_i|-1)) × Σ MRD_ij
    """
    if len(category_mrs) <= 1:
        return 0.0

    ki = kill_vectors.get(mr_id)
    if ki is None:
        raise ValueError(f"missing kill vector: {mr_id}")

    total_mrd = 0.0
    count = 0

    for other_id in category_mrs:
        if other_id == mr_id:
            continue

        kj = kill_vectors.get(other_id)
        if kj is None:
            raise ValueError(f"missing kill vector: {other_id}")

        total_mrd += compute_jaccard_distance(ki, kj)
        count += 1

    return total_mrd / count
