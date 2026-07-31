"""Chain backend module for MPSC"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TransactionReceipt:
    """Receipt of a transaction"""

    tx_hash: str
    contract_address: str | None = None
    gas_used: int = 0
    success: bool = True
    logs: list[dict] = field(default_factory=list)


@dataclass
class ChainState:
    """State observation from chain"""

    block_number: int = 0
    timestamp: int = 0
    balances: dict[str, int] = field(default_factory=dict)
    storage: dict[str, Any] = field(default_factory=dict)


class ChainBackend(ABC):
    """Abstract base class for chain backends"""

    @abstractmethod
    def get_accounts(self) -> list[str]:
        """Get available accounts"""
        ...

    @abstractmethod
    def get_balance(self, address: str) -> int:
        """Get balance of an address in wei"""
        ...

    @abstractmethod
    def deploy(
        self,
        bytecode: str,
        abi: list[dict],
        args: list[Any] | None = None,
        sender: str | None = None,
        value: int = 0,
        gas_limit: int | None = None,
    ) -> TransactionReceipt:
        """Deploy a contract"""
        ...

    @abstractmethod
    def call(
        self,
        contract_address: str,
        abi: list[dict],
        function_name: str,
        args: list[Any] | None = None,
        sender: str | None = None,
        value: int = 0,
        gas_limit: int | None = None,
    ) -> tuple[Any, TransactionReceipt]:
        """Call a contract function"""
        ...

    @abstractmethod
    def get_state(self, contract_address: str, abi: list[dict]) -> ChainState:
        """Get current chain state"""
        ...

    @abstractmethod
    def reset(self) -> None:
        """Reset the chain state"""
        ...
