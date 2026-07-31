"""Tests for mutation score computation"""

import pytest
from mpsc.models import KillVector
from mpsc.mutation.mutation_score import (
    compute_average_mutation_score,
    compute_kill_vector,
    compute_mutation_score,
)


def test_compute_kill_vector():
    """Test kill vector computation"""
    kv = compute_kill_vector(
        mr_id="MR1",
        mutant_ids=["m1", "m2", "m3"],
        detection_counts={"m1": 5, "m2": 0, "m3": 3},
        total_executions={"m1": 10, "m2": 10, "m3": 10},
        tau=0.1,
    )

    assert kv.kills["m1"] is True  # 5/10 = 0.5 >= 0.1
    assert kv.kills["m2"] is False  # 0/10 = 0 < 0.1
    assert kv.kills["m3"] is True  # 3/10 = 0.3 >= 0.1


def test_compute_mutation_score():
    """Test mutation score computation"""
    kv = KillVector(
        mr_id="MR1",
        kills={"m1": True, "m2": False, "m3": True, "m4": True},
    )

    ms = compute_mutation_score(kv)
    assert ms == 0.75  # 3/4


def test_compute_average_mutation_score():
    """Test average mutation score computation"""
    scores = [0.8, 0.6, 0.9, 0.7]

    avg = compute_average_mutation_score(scores)
    assert avg == 0.75


def test_kill_vector_rejects_missing_or_invalid_cell_counts():
    with pytest.raises(ValueError, match="incomplete cell counts"):
        compute_kill_vector("MR1", ["m1"], {}, {"m1": 10})

    with pytest.raises(ValueError, match="invalid counts"):
        compute_kill_vector(
            "MR1",
            ["m1"],
            {"m1": 11},
            {"m1": 10},
        )
