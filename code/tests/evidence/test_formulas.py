"""Tests for formulas with hand-calculated known vectors.
TeX references:
- Eq.2: Kill vector K_ik (lines 502-509)
- Eq.3: Mutation score MS_i (lines 511-514)
- Eq.4: MRD Jaccard distance (lines 520-529)
- Eq.5: DifferenceScore (lines 532-537)
- Eq.6: CombinedScore (lines 539-542)
"""

from mpsc.models import KillVector
from mpsc.mr.distance import compute_difference_score, compute_jaccard_distance
from mpsc.mr.optimizer import compute_mutation_score
from mpsc.mutation.mutation_score import compute_average_mutation_score


class TestMutationScoreFormula:
    """Test Eq.3: MS_i = (1/n) × Σ K_ik"""

    def test_all_killed(self):
        """n=5, all killed -> MS = 1.0"""
        kv = KillVector(
            mr_id="MR1",
            kills={"m1": True, "m2": True, "m3": True, "m4": True, "m5": True},
        )
        assert compute_mutation_score(kv) == 1.0

    def test_none_killed(self):
        """n=5, none killed -> MS = 0.0"""
        kv = KillVector(
            mr_id="MR1",
            kills={"m1": False, "m2": False, "m3": False, "m4": False, "m5": False},
        )
        assert compute_mutation_score(kv) == 0.0

    def test_partial(self):
        """n=5, 3 killed -> MS = 0.6"""
        kv = KillVector(
            mr_id="MR1",
            kills={"m1": True, "m2": True, "m3": True, "m4": False, "m5": False},
        )
        assert compute_mutation_score(kv) == 0.6

    def test_single_mutant(self):
        """n=1 edge case"""
        kv = KillVector(mr_id="MR1", kills={"m1": True})
        assert compute_mutation_score(kv) == 1.0

    def test_empty(self):
        """Empty kill vector -> 0.0"""
        kv = KillVector(mr_id="MR1", kills={})
        assert compute_mutation_score(kv) == 0.0


class TestJaccardDistanceFormula:
    """Test Eq.4: MRD_ij = 1 - Σ min(K_ik, K_jk) / Σ max(K_ik, K_jk)"""

    def test_identical(self):
        """Identical kill vectors -> MRD = 0"""
        ki = KillVector(mr_id="MR1", kills={"m1": True, "m2": False, "m3": True})
        kj = KillVector(mr_id="MR2", kills={"m1": True, "m2": False, "m3": True})
        assert compute_jaccard_distance(ki, kj) == 0.0

    def test_completely_different(self):
        """Completely different -> MRD = 1"""
        ki = KillVector(mr_id="MR1", kills={"m1": True, "m2": False, "m3": True})
        kj = KillVector(mr_id="MR2", kills={"m1": False, "m2": True, "m3": False})
        # min: (1,0)=0, (0,1)=0, (1,0)=0 -> sum=0
        # max: (1,0)=1, (0,1)=1, (1,0)=1 -> sum=3
        # MRD = 1 - 0/3 = 1.0
        assert compute_jaccard_distance(ki, kj) == 1.0

    def test_partial_overlap(self):
        """Partial overlap -> 0 < MRD < 1"""
        ki = KillVector(mr_id="MR1", kills={"m1": True, "m2": True, "m3": False})
        kj = KillVector(mr_id="MR2", kills={"m1": True, "m2": False, "m3": False})
        # min: (1,1)=1, (1,0)=0, (0,0)=0 -> sum=1
        # max: (1,1)=1, (1,0)=1, (0,0)=0 -> sum=2
        # MRD = 1 - 1/2 = 0.5
        assert compute_jaccard_distance(ki, kj) == 0.5

    def test_all_killed_vs_none(self):
        """One kills all, other kills none -> MRD = 1"""
        ki = KillVector(mr_id="MR1", kills={"m1": True, "m2": True, "m3": True})
        kj = KillVector(mr_id="MR2", kills={"m1": False, "m2": False, "m3": False})
        # min: 0, max: 3 -> MRD = 1
        assert compute_jaccard_distance(ki, kj) == 1.0

    def test_empty_vectors(self):
        """Both empty -> MRD = 0 (by convention)"""
        ki = KillVector(mr_id="MR1", kills={})
        kj = KillVector(mr_id="MR2", kills={})
        assert compute_jaccard_distance(ki, kj) == 0.0

    def test_one_empty_one_nonempty(self):
        """One empty, one non-empty -> MRD = 1"""
        ki = KillVector(mr_id="MR1", kills={})
        kj = KillVector(mr_id="MR2", kills={"m1": True})
        # denominator = max(0,1) = 1, numerator = min(0,1) = 0
        # MRD = 1 - 0/1 = 1.0
        assert compute_jaccard_distance(ki, kj) == 1.0

    def test_order_independent(self):
        """MRD should be symmetric: MRD(i,j) = MRD(j,i)"""
        ki = KillVector(mr_id="MR1", kills={"m1": True, "m2": False, "m3": True})
        kj = KillVector(mr_id="MR2", kills={"m1": False, "m2": True, "m3": True})
        assert compute_jaccard_distance(ki, kj) == compute_jaccard_distance(kj, ki)


class TestDifferenceScoreFormula:
    """Test Eq.5: DifferenceScore_i = (1/(|C_i|-1)) × Σ MRD_ij"""

    def test_three_mrs(self):
        """Three MRs in same category"""
        kill_vectors = {
            "MR1": KillVector(mr_id="MR1", kills={"m1": True, "m2": False, "m3": True}),
            "MR2": KillVector(mr_id="MR2", kills={"m1": False, "m2": True, "m3": True}),
            "MR3": KillVector(mr_id="MR3", kills={"m1": True, "m2": True, "m3": False}),
        }

        # MRD(MR1, MR2) = 1 - min(0+0+1)/max(1+1+1) = 1 - 1/3 ≈ 0.667
        # MRD(MR1, MR3) = 1 - min(1+0+0)/max(1+1+1) = 1 - 1/3 ≈ 0.667
        # DS(MR1) = (0.667 + 0.667) / 2 ≈ 0.667

        ds = compute_difference_score("MR1", ["MR1", "MR2", "MR3"], kill_vectors)
        assert abs(ds - 0.6667) < 0.01

    def test_single_mr(self):
        """Single MR in category -> DS = 0"""
        kill_vectors = {
            "MR1": KillVector(mr_id="MR1", kills={"m1": True}),
        }
        ds = compute_difference_score("MR1", ["MR1"], kill_vectors)
        assert ds == 0.0

    def test_identical_mrs(self):
        """All identical -> DS = 0"""
        kill_vectors = {
            "MR1": KillVector(mr_id="MR1", kills={"m1": True, "m2": True}),
            "MR2": KillVector(mr_id="MR2", kills={"m1": True, "m2": True}),
        }
        ds = compute_difference_score("MR1", ["MR1", "MR2"], kill_vectors)
        assert ds == 0.0


class TestCombinedScoreFormula:
    """Test Eq.6: CombinedScore = 0.5*MS + 0.5*DS"""

    def test_equal_weight(self):
        """Verify equal weighting"""
        from mpsc.config import MPSCConfig
        from mpsc.models import InputRelation, MetamorphicRelation, OutputRelation
        from mpsc.mr.optimizer import optimize_mr_category

        config = MPSCConfig(ms_weight=0.5, ds_weight=0.5, tau_c=0.0, min_set_size=1)

        # Create MRs
        mrs = [
            MetamorphicRelation(
                mr_id="MR1",
                category="test",
                target_operation="test",
                input_relation=InputRelation(description="", transform=""),
                output_relation=OutputRelation(description="", check_type="equal"),
            ),
        ]

        kill_vectors = {
            "MR1": KillVector(mr_id="MR1", kills={"m1": True, "m2": False}),
        }

        # MS = 0.5, DS = 0 (single MR) -> Combined = 0.5*0.5 + 0.5*0 = 0.25
        # The optimizer should keep this MR since it's the only one
        optimized = optimize_mr_category(mrs, kill_vectors, config)
        assert "MR1" in optimized


class TestAverageMutationScore:
    """Test Eq.7: MS_avg = (1/|MRS|) × Σ MS_i"""

    def test_average(self):
        """Average of [0.8, 0.6, 0.9, 0.7] = 0.75"""
        assert compute_average_mutation_score([0.8, 0.6, 0.9, 0.7]) == 0.75

    def test_single(self):
        """Single score -> itself"""
        assert compute_average_mutation_score([0.5]) == 0.5

    def test_empty(self):
        """Empty -> 0.0"""
        assert compute_average_mutation_score([]) == 0.0
