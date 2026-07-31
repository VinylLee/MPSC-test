"""Transaction module for MPSC"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..models import ExecutionObservation
from .backend import TransactionReceipt


@dataclass
class TransactionResult:
    """Result of a transaction"""

    receipt: TransactionReceipt
    return_value: Any = None
    observation: ExecutionObservation | None = None


def build_observation(
    receipt: TransactionReceipt,
    return_value: Any = None,
    state_changes: dict[str, Any] | None = None,
) -> ExecutionObservation:
    """Build an observation from transaction result"""
    return ExecutionObservation(
        success=receipt.success,
        return_value=return_value,
        reverted=not receipt.success,
        revert_reason="" if receipt.success else "Transaction reverted",
        events=receipt.logs,
        state_changes=state_changes or {},
        gas_used=receipt.gas_used,
    )
