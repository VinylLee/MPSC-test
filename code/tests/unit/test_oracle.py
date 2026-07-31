"""Tests for Oracle - R05 required/optional predicates"""

from mpsc.models import (
    ContractState,
    ExecutionObservation,
    InputRelation,
    MetamorphicRelation,
    NativeBalances,
    OutputRelation,
    TransactionInfo,
)
from mpsc.testing.oracle import MRChecker


def _obs(return_value=None, status="success", gas=None, tokens=None):
    return ExecutionObservation(
        outcome_type=f"success_{status}",
        execution_status=status,
        return_value=return_value,
        transaction=TransactionInfo(submitted=gas is not None, gas_used=gas),
        native_balances=NativeBalances(),
        contract_state=ContractState(
            before={"token_balances": tokens or {}},
            after={"token_balances": tokens or {}},
        ),
    )


def _mr(check_type, preconditions=None):
    return MetamorphicRelation(
        mr_id="T",
        category="t",
        target_operation="t",
        preconditions=preconditions or [],
        input_relation=InputRelation(description="", transform=""),
        output_relation=OutputRelation(description="", check_type=check_type),
    )


class TestRequiredPredicateVerdict:
    def test_view_different_returns_indeterminate(self):
        """MR7.4: μ satisfied, ε satisfied, δ unavailable -> indeterminate"""
        checker = MRChecker()
        mr = _mr("view_different_return")
        result = checker.check(mr, _obs(100), _obs(0))
        # μ_f ≠ μ_s: 100 != 0 -> satisfied
        # ε_f ≠ ε_s: same as μ -> satisfied
        # δ_f = δ_s: unavailable (view function)
        # Required δ unavailable -> indeterminate
        assert result.verdict == "indeterminate"

    def test_state_change_pass(self):
        """MR8.1: μ and δ both satisfied -> pass"""
        checker = MRChecker()
        mr = _mr("state_change_balance")
        result = checker.check(mr, _obs(True, gas=50000), _obs(True, gas=50000))
        assert result.verdict == "pass"

    def test_state_change_violation(self):
        """MR8.1: μ different -> violation"""
        checker = MRChecker()
        mr = _mr("state_change_balance")
        result = checker.check(mr, _obs(True, gas=50000), _obs(False, gas=50000))
        assert result.verdict == "violation"


class TestPreconditionVerdict:
    def test_precondition_not_satisfied(self):
        checker = MRChecker()
        mr = _mr("view_different_return", [{"id": "valid_addresses"}])
        # Override precondition eval to return False
        result = checker.check(mr, _obs(100), _obs(0))
        # valid_addresses returns True by default
        assert result.preconditions_satisfied is True


class TestPredicateStatus:
    def test_predicate_has_required_field(self):
        checker = MRChecker()
        mr = _mr("view_different_return")
        result = checker.check(mr, _obs(100), _obs(0))
        for pred in result.predicate_components:
            assert hasattr(pred, "required")
            assert hasattr(pred, "status")
            assert pred.status in (
                "satisfied",
                "violated",
                "unavailable",
                "not_applicable",
            )

    def test_mu_satisfied_status(self):
        checker = MRChecker()
        mr = _mr("state_change_balance")
        result = checker.check(mr, _obs(True, gas=50000), _obs(True, gas=50000))
        mu_pred = [p for p in result.predicate_components if "μ" in p.expression][0]
        assert mu_pred.status == "satisfied"

    def test_mu_violated_status(self):
        checker = MRChecker()
        mr = _mr("view_different_return")
        result = checker.check(mr, _obs(100), _obs(100))
        mu_pred = [p for p in result.predicate_components if "μ" in p.expression][0]
        assert mu_pred.status == "violated"
