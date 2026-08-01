"""Test executor for MPSC - uses refactored observation model"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import (
    ExecutionObservation,
    MetamorphicRelation,
    MRViolation,
    TestCase,
)
from .oracle import MRChecker

if TYPE_CHECKING:
    pass


class TestExecutor:
    def __init__(self, backend) -> None:
        self.backend = backend
        self.checker = MRChecker()

    def execute_test_case(
        self,
        contract_address: str,
        abi: list[dict],
        function_name: str,
        test_case: TestCase,
        accounts_to_track: list[str] | None = None,
        is_view: bool = False,
    ) -> ExecutionObservation:
        try:
            return self.backend.execute_and_observe(
                contract_address=contract_address,
                abi=abi,
                function_name=function_name,
                args=list(test_case.inputs.values()) if test_case.inputs else None,
                sender=test_case.caller,
                value=test_case.value,
                gas_limit=test_case.gas_limit,
                accounts_to_track=accounts_to_track or [],
                is_view=is_view,
            )
        except Exception as e:
            from ..testing.outcomes import classify_web3_error

            outcome = classify_web3_error(e)
            return ExecutionObservation(
                outcome_type=outcome,
                execution_status=outcome.value,
                error={"type": type(e).__name__, "message": str(e)},
            )

    def execute_mr_test(
        self,
        contract_address: str,
        abi: list[dict],
        function_name: str,
        mr: MetamorphicRelation,
        source_test: TestCase,
        followup_test: TestCase,
        accounts_to_track: list[str] | None = None,
        is_view: bool = False,
    ) -> MRViolation:
        source_obs = self.execute_test_case(
            contract_address,
            abi,
            function_name,
            source_test,
            accounts_to_track=accounts_to_track,
            is_view=is_view,
        )
        followup_obs = self.execute_test_case(
            contract_address,
            abi,
            function_name,
            followup_test,
            accounts_to_track=accounts_to_track,
            is_view=is_view,
        )

        oracle_result = self.checker.check(mr, source_obs, followup_obs)

        return MRViolation(
            mr=mr,
            source_test=source_test,
            followup_test=followup_test,
            source_observation=source_obs,
            followup_observation=followup_obs,
            oracle_result=oracle_result,
            violated=oracle_result.violation is True,
            reason=oracle_result.explanation,
        )
