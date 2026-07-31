"""Tests for MR distance computation"""

from mpsc.models import KillVector
from mpsc.mr.distance import compute_difference_score, compute_jaccard_distance


def test_jaccard_distance_identical():
    """Test Jaccard distance for identical kill vectors"""
    ki = KillVector(mr_id="MR1", kills={"m1": True, "m2": False, "m3": True})
    kj = KillVector(mr_id="MR2", kills={"m1": True, "m2": False, "m3": True})

    distance = compute_jaccard_distance(ki, kj)
    assert distance == 0.0


def test_jaccard_distance_different():
    """Test Jaccard distance for completely different kill vectors"""
    ki = KillVector(mr_id="MR1", kills={"m1": True, "m2": False, "m3": True})
    kj = KillVector(mr_id="MR2", kills={"m1": False, "m2": True, "m3": False})

    distance = compute_jaccard_distance(ki, kj)
    assert distance == 1.0


def test_jaccard_distance_partial():
    """Test Jaccard distance for partially overlapping kill vectors"""
    ki = KillVector(mr_id="MR1", kills={"m1": True, "m2": True, "m3": False})
    kj = KillVector(mr_id="MR2", kills={"m1": True, "m2": False, "m3": False})

    distance = compute_jaccard_distance(ki, kj)
    # min: (1,1)=1, (1,0)=0, (0,0)=0 -> sum=1
    # max: (1,1)=1, (1,0)=1, (0,0)=0 -> sum=2
    # MRD = 1 - 1/2 = 0.5
    assert distance == 0.5


def test_jaccard_distance_empty():
    """Test Jaccard distance for empty kill vectors"""
    ki = KillVector(mr_id="MR1", kills={})
    kj = KillVector(mr_id="MR2", kills={})

    distance = compute_jaccard_distance(ki, kj)
    assert distance == 0.0


def test_difference_score():
    """Test DifferenceScore computation"""
    kill_vectors = {
        "MR1": KillVector(mr_id="MR1", kills={"m1": True, "m2": False, "m3": True}),
        "MR2": KillVector(mr_id="MR2", kills={"m1": False, "m2": True, "m3": True}),
        "MR3": KillVector(mr_id="MR3", kills={"m1": True, "m2": True, "m3": False}),
    }

    category_mrs = ["MR1", "MR2", "MR3"]

    ds = compute_difference_score("MR1", category_mrs, kill_vectors)
    assert 0.0 <= ds <= 1.0


def test_distance_uses_union_for_different_vector_domains():
    assert (
        compute_jaccard_distance(
            KillVector("MR1", {"m1": True}),
            KillVector("MR2", {"m2": True}),
        )
        == 1.0
    )
