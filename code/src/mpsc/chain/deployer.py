"""Deployer module for MPSC"""

from __future__ import annotations

from typing import Any

from .backend import ChainBackend, TransactionReceipt


class ContractDeployer:
    """Deploy and interact with contracts"""

    def __init__(self, backend: ChainBackend) -> None:
        self.backend = backend
        self._deployed: dict[str, str] = {}  # name -> address

    def deploy(
        self,
        contract_name: str,
        bytecode: str,
        abi: list[dict],
        args: list[Any] | None = None,
        sender: str | None = None,
        value: int = 0,
    ) -> str:
        """Deploy a contract and return its address"""
        receipt = self.backend.deploy(
            bytecode=bytecode,
            abi=abi,
            args=args,
            sender=sender,
            value=value,
        )

        if not receipt.success:
            raise RuntimeError(f"Deployment failed: {receipt}")

        if receipt.contract_address is None:
            raise RuntimeError("No contract address in receipt")

        self._deployed[contract_name] = receipt.contract_address
        return receipt.contract_address

    def get_address(self, contract_name: str) -> str | None:
        """Get deployed contract address"""
        return self._deployed.get(contract_name)

    def call(
        self,
        contract_address: str,
        abi: list[dict],
        function_name: str,
        args: list[Any] | None = None,
        sender: str | None = None,
        value: int = 0,
    ) -> tuple[Any, TransactionReceipt]:
        """Call a contract function"""
        return self.backend.call(
            contract_address=contract_address,
            abi=abi,
            function_name=function_name,
            args=args,
            sender=sender,
            value=value,
        )
