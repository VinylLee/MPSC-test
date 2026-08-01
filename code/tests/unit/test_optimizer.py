"""Tests for MR optimizer"""

import pytest
from mpsc.config import MPSCConfig
from mpsc.models import (
    InputRelation,
    KillVector,
    MetamorphicRelation,
    OutputRelation,
)
from mpsc.mr.optimizer import (
    compute_mutation_score,
    optimize_mr_category,
    optimize_mr_category_with_trace,
)


def test_compute_mutation_score():
    """Test mutation score computation"""
    kv = KillVector(
        mr_id="MR1",
        kills={"m1": True, "m2": False, "m3": True, "m4": True, "m5": False},
    )

    ms = compute_mutation_score(kv)
    assert ms == 0.6  # 3/5


def test_compute_mutation_score_empty():
    """Test mutation score for empty kill vector"""
    kv = KillVector(mr_id="MR1", kills={})

    ms = compute_mutation_score(kv)
    assert ms == 0.0


def test_optimize_mr_category():
    """Test MR optimization for a category"""
    mrs = [
        MetamorphicRelation(
            mr_id="MR1",
            category="test",
            target_operation="test",
            input_relation=InputRelation(description="", transform=""),
            output_relation=OutputRelation(description="", check_type="equal"),
        ),
        MetamorphicRelation(
            mr_id="MR2",
            category="test",
            target_operation="test",
            input_relation=InputRelation(description="", transform=""),
            output_relation=OutputRelation(description="", check_type="equal"),
        ),
        MetamorphicRelation(
            mr_id="MR3",
            category="test",
            target_operation="test",
            input_relation=InputRelation(description="", transform=""),
            output_relation=OutputRelation(description="", check_type="equal"),
        ),
    ]

    kill_vectors = {
        "MR1": KillVector(mr_id="MR1", kills={"m1": True, "m2": True, "m3": True}),
        "MR2": KillVector(mr_id="MR2", kills={"m1": False, "m2": False, "m3": False}),
        "MR3": KillVector(mr_id="MR3", kills={"m1": True, "m2": False, "m3": True}),
    }

    config = MPSCConfig(tau_c=0.3, min_set_size=1)

    optimized = optimize_mr_category(mrs, kill_vectors, config)

    # MR2 has lowest mutation score, should be pruned first
    assert len(optimized) <= len(mrs)
    assert "MR1" in optimized  # High mutation score


def test_optimizer_requires_unknown_parameters_explicitly():
    mrs = [_mr("MR1")]
    vectors = {"MR1": KillVector("MR1", {"m1": True})}

    with pytest.raises(ValueError, match="tau_c is unknown"):
        optimize_mr_category(mrs, vectors, MPSCConfig())

    with pytest.raises(ValueError, match="min_set_size is unknown"):
        optimize_mr_category(
            mrs,
            vectors,
            MPSCConfig(tau_c=0.5),
        )


def test_tie_break_is_deterministic_by_mr_id():
    mrs = [_mr("MR2"), _mr("MR1"), _mr("MR3")]
    vectors = {mr.mr_id: KillVector(mr.mr_id, {"m1": False}) for mr in mrs}
    trace = optimize_mr_category_with_trace(
        mrs,
        vectors,
        MPSCConfig(tau_c=0.1, min_set_size=2),
    )

    assert trace["iterations"][0]["weakest_mr"] == "MR1"
    assert trace["optimized_mrs"] == ["MR2", "MR3"]


def test_optimizer_rejects_different_mutant_domains():
    mrs = [_mr("MR1"), _mr("MR2")]
    vectors = {
        "MR1": KillVector("MR1", {"m1": True}),
        "MR2": KillVector("MR2", {"m2": True}),
    }

    with pytest.raises(ValueError, match="same non-empty mutant set"):
        optimize_mr_category(
            mrs,
            vectors,
            MPSCConfig(tau_c=0.5, min_set_size=1),
        )


def _mr(mr_id: str) -> MetamorphicRelation:
    return MetamorphicRelation(
        mr_id=mr_id,
        category="test",
        target_operation="test",
        input_relation=InputRelation(description="", transform=""),
        output_relation=OutputRelation(description="", check_type="equal"),
    )
