"""Test case generator for MPSC"""

from __future__ import annotations

import random
from typing import Any

from ..models import MetamorphicRelation, MutableParameter, TestCase


class TestCaseGenerator:
    """Generate test cases for metamorphic testing"""

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def generate_source_case(
        self,
        mr: MetamorphicRelation,
        parameters: list[MutableParameter],
        accounts: list[str],
    ) -> TestCase:
        """Generate a source test case"""
        inputs: dict[str, Any] = {}
        caller = accounts[0] if accounts else None
        value = 0

        for param in parameters:
            if param.valid_values:
                inputs[param.name] = self._rng.choice(param.valid_values)
            elif param.variation_space:
                inputs[param.name] = self._rng.choice(param.variation_space)

        return TestCase(inputs=inputs, caller=caller, value=value)

    def generate_followup_case(
        self,
        source: TestCase,
        mr: MetamorphicRelation,
    ) -> TestCase:
        """Generate a follow-up test case from source according to MR"""
        # Default: copy source
        followup = TestCase(
            inputs=dict(source.inputs),
            caller=source.caller,
            value=source.value,
        )

        # Apply MR transformation (to be specialized per MR category)
        return followup

    def generate_boundary_cases(
        self,
        parameters: list[MutableParameter],
        accounts: list[str],
    ) -> list[TestCase]:
        """Generate boundary value test cases"""
        cases: list[TestCase] = []

        for param in parameters:
            if param.invalid_values:
                for val in param.invalid_values[:2]:  # limit to 2
                    cases.append(TestCase(inputs={param.name: val}))

        return cases
