"""Execution outcome classification for MPSC"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class OutcomeType(Enum):
    """Classification of execution outcomes"""

    SUCCESS_VIEW_CALL = "success_view_call"
    SUCCESS_TRANSACTION = "success_transaction"
    EVM_REVERT = "evm_revert"
    OUT_OF_GAS = "out_of_gas"
    ABI_ENCODING_ERROR = "abi_encoding_error"
    INPUT_GENERATION_ERROR = "input_generation_error"
    RPC_ERROR = "rpc_error"
    DEPLOYMENT_ERROR = "deployment_error"
    UNSUPPORTED = "unsupported"


@dataclass
class ExecutionOutcome:
    """Structured execution outcome"""

    outcome_type: OutcomeType
    success: bool
    return_value: Any = None
    error_message: str | None = None
    error_details: dict[str, Any] = field(default_factory=dict)

    @property
    def is_evm_execution(self) -> bool:
        """Whether this outcome reached the EVM"""
        return self.outcome_type in (
            OutcomeType.SUCCESS_VIEW_CALL,
            OutcomeType.SUCCESS_TRANSACTION,
            OutcomeType.EVM_REVERT,
            OutcomeType.OUT_OF_GAS,
        )

    @property
    def is_pre_evm_failure(self) -> bool:
        """Whether this outcome failed before reaching EVM"""
        return self.outcome_type in (
            OutcomeType.ABI_ENCODING_ERROR,
            OutcomeType.INPUT_GENERATION_ERROR,
            OutcomeType.RPC_ERROR,
            OutcomeType.DEPLOYMENT_ERROR,
        )


def classify_web3_error(error: Exception) -> OutcomeType:
    """Classify a Web3/Python exception into an outcome type"""
    error_str = str(error).lower()
    type(error).__name__

    # ABI encoding errors
    if "encoding" in error_str or "abi" in error_str or "type" in error_str:
        return OutcomeType.ABI_ENCODING_ERROR

    # Web3 contract call errors that indicate ABI issues
    if "could not identify" in error_str or "argument" in error_str:
        return OutcomeType.ABI_ENCODING_ERROR

    # Solidity revert
    if "revert" in error_str or "execution reverted" in error_str:
        return OutcomeType.EVM_REVERT

    # Out of gas
    if "out of gas" in error_str:
        return OutcomeType.OUT_OF_GAS

    # RPC errors
    if "rpc" in error_str or "provider" in error_str or "connection" in error_str:
        return OutcomeType.RPC_ERROR

    # Default to EVM revert if we can't classify
    return OutcomeType.EVM_REVERT
