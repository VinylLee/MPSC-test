"""Core data models for MPSC"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class ParameterType(Enum):
    FUNCTION_ARGUMENT = "function_argument"
    CALLER_IDENTITY = "caller_identity"
    DEPLOYMENT_ACCOUNT = "deployment_account"
    COMPILER_VERSION = "compiler_version"
    GAS_LIMIT = "gas_limit"
    DEPLOYMENT_ENVIRONMENT = "deployment_environment"
    ADDRESS = "address"
    AMOUNT = "amount"
    OTHER = "other"


@dataclass
class MutableParameter:
    name: str
    param_type: ParameterType
    source: str
    variation_space: list[Any] = field(default_factory=list)
    valid_values: list[Any] = field(default_factory=list)
    invalid_values: list[Any] = field(default_factory=list)
    description: str = ""


@dataclass
class InputRelation:
    description: str
    transform: str


@dataclass
class OutputRelation:
    description: str
    check_type: str
    fields: list[str] = field(default_factory=list)
    expression: str = ""


@dataclass
class MetamorphicRelation:
    mr_id: str
    category: str
    target_operation: str
    preconditions: list[dict[str, Any]] = field(default_factory=list)
    input_relation: InputRelation | None = None
    output_relation: OutputRelation | None = None
    description: str = ""
    executable: bool = True
    missing_information: list[str] = field(default_factory=list)


@dataclass
class TestCase:
    inputs: dict[str, Any] = field(default_factory=dict)
    caller: str | None = None
    value: int = 0
    gas_limit: int | None = None


# --- Refactored Observation Model ---
# Strict separation: native_balances, contract_state, transaction


@dataclass
class TransactionInfo:
    """Transaction receipt information"""

    submitted: bool = False
    hash: str | None = None
    receipt_status: int | None = None
    block_number: int | None = None
    gas_used: int | None = None


@dataclass
class NativeBalances:
    """ETH native balances (NOT token balances)"""

    before: dict[str, int] = field(default_factory=dict)
    after: dict[str, int] = field(default_factory=dict)
    delta: dict[str, int] = field(default_factory=dict)


@dataclass
class ContractState:
    """Contract state - specifically token balances for MyToken"""

    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)
    delta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionObservation:
    """Complete execution observation with strict namespace separation"""

    outcome_type: str = "success_view_call"  # OutcomeType.value string
    execution_status: str = "success"
    return_value: Any = None
    transaction: TransactionInfo = field(default_factory=TransactionInfo)
    native_balances: NativeBalances = field(default_factory=NativeBalances)
    contract_state: ContractState = field(default_factory=ContractState)
    events: list[dict] = field(default_factory=list)
    error: dict[str, Any] | None = None


# --- Predicate-based Oracle ---


@dataclass
class PredicateComponent:
    """A single predicate from the MR definition"""

    expression: str  # e.g., "μ_f != μ_s"
    required: bool = True  # True = required, False = optional
    status: str = "unavailable"  # satisfied, violated, unavailable, not_applicable
    source_value: Any = None
    followup_value: Any = None
    reason: str | None = None


@dataclass
class OracleResult:
    """Oracle result with explicit predicate components"""

    preconditions_satisfied: bool = True
    preconditions_details: list[dict] = field(default_factory=list)
    predicate_components: list[PredicateComponent] = field(default_factory=list)
    relation_satisfied: bool | None = None
    violation: bool | None = None
    verdict: Literal[
        "pass", "violation", "invalid_test", "indeterminate", "unsupported"
    ] = "indeterminate"
    explanation: str = ""


@dataclass
class MRViolation:
    """Result of checking an MR"""

    mr: MetamorphicRelation
    source_test: TestCase
    followup_test: TestCase
    source_observation: ExecutionObservation
    followup_observation: ExecutionObservation
    oracle_result: OracleResult | None = None
    violated: bool = False
    reason: str = ""


@dataclass
class KillVector:
    mr_id: str
    kills: dict[str, bool] = field(default_factory=dict)


@dataclass
class MROptimizationResult:
    original_mrs: list[str] = field(default_factory=list)
    optimized_mrs: list[str] = field(default_factory=list)
    mutation_scores: dict[str, float] = field(default_factory=dict)
    difference_scores: dict[str, float] = field(default_factory=dict)
    combined_scores: dict[str, float] = field(default_factory=dict)
