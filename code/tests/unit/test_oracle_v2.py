"""Tests for Oracle v2 - R05 predicate model"""

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


class TestPredicateComponents:
    def test_view_different_has_3_components(self):
        """MR7.4 has μ, ε, δ predicates"""
        checker = MRChecker()
        mr = _mr("view_different_return")
        result = checker.check(mr, _obs(100), _obs(0))
        assert len(result.predicate_components) == 3

    def test_different_returns_verdict_indeterminate(self):
        """MR7.4: δ unavailable -> indeterminate even though μ satisfied"""
        checker = MRChecker()
        mr = _mr("view_different_return")
        result = checker.check(mr, _obs(100), _obs(0))
        assert result.verdict == "indeterminate"

    def test_state_change_verdict_pass(self):
        """MR8.1: both μ and δ satisfied -> pass"""
        checker = MRChecker()
        mr = _mr("state_change_balance")
        result = checker.check(mr, _obs(True, gas=50000), _obs(True, gas=50000))
        assert result.verdict == "pass"


class TestPredicateFields:
    def test_has_status_field(self):
        checker = MRChecker()
        mr = _mr("view_different_return")
        result = checker.check(mr, _obs(100), _obs(0))
        pred = result.predicate_components[0]
        assert hasattr(pred, "status")
        assert pred.status in ("satisfied", "violated", "unavailable", "not_applicable")

    def test_has_required_field(self):
        checker = MRChecker()
        mr = _mr("view_different_return")
        result = checker.check(mr, _obs(100), _obs(0))
        pred = result.predicate_components[0]
        assert hasattr(pred, "required")
        assert isinstance(pred.required, bool)
