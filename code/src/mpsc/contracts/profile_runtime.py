"""Behavioral runtime for ABI-verified contract profiles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eth_abi import decode

from ..chain.backend import TransactionReceipt
from ..chain.local_backend import LocalChainBackend
from .profile import (
    compile_named_contract,
    compile_profile_contract,
    load_contract_profile,
)


@dataclass
class DeployedProfile:
    """One isolated local-chain deployment of a contract profile."""

    profile: dict[str, Any]
    abi: list[dict[str, Any]]
    backend: LocalChainBackend
    contract_address: str
    roles: dict[str, str]
    dependencies: dict[str, str]
    deployment_receipt: TransactionReceipt

    def _function(self, alias: str) -> dict[str, Any]:
        try:
            return self.profile["functions"][alias]
        except KeyError as error:
            raise KeyError(f"Unknown profile function alias {alias!r}") from error

    def call(
        self,
        alias: str,
        arguments: list[Any] | None = None,
        caller_role: str = "owner",
    ) -> Any:
        """Call one read-only ABI function by stable profile alias."""

        function = self._function(alias)
        if function.get("abi_type", "function") != "function":
            raise ValueError(f"{alias!r} is not an ABI function")
        return self.backend.call_view(
            self.contract_address,
            self.abi,
            function["solidity_name"],
            arguments,
            self.roles[caller_role],
        )

    def transact(
        self,
        alias: str,
        arguments: list[Any] | None = None,
        caller_role: str = "owner",
        value: int = 0,
    ) -> TransactionReceipt:
        """Submit one ABI transaction by stable profile alias."""

        function = self._function(alias)
        if function.get("abi_type", "function") != "function":
            raise ValueError(f"{alias!r} is not an ABI function")
        _, receipt = self.backend.send_transaction(
            self.contract_address,
            self.abi,
            function["solidity_name"],
            arguments,
            self.roles[caller_role],
            value,
        )
        return receipt

    def observe(
        self,
        observer_id: str,
        arguments: list[Any] | None = None,
        caller_role: str = "owner",
    ) -> Any:
        """Execute a declared observer and decode its result."""

        try:
            observer = next(
                item
                for item in self.profile["state_observers"]
                if item["id"] == observer_id
            )
        except StopIteration as error:
            raise KeyError(f"Unknown observer {observer_id!r}") from error

        if observer.get("kind", "function") == "raw_selector":
            raw = self.backend.call_raw(
                self.contract_address,
                bytes.fromhex(observer["selector"].removeprefix("0x")),
                self.roles[caller_role],
            )
            return decode([observer["decode"]], raw)[0]
        return self.call(observer["function"], arguments, caller_role)


def _resolve_value(
    value: Any,
    roles: dict[str, str],
    dependencies: dict[str, str],
) -> Any:
    if isinstance(value, dict) and "role" in value:
        return roles[value["role"]]
    if isinstance(value, dict) and "contract" in value:
        return dependencies[value["contract"]]
    return value


def deploy_profile(
    path: str | Path,
    *,
    run_initialization: bool = True,
) -> DeployedProfile:
    """Compile, deploy, and optionally initialize one profile on a fresh chain."""

    profile = load_contract_profile(path)
    artifact = compile_profile_contract(profile)
    backend = LocalChainBackend()
    accounts = backend.get_accounts()
    roles = {
        role: accounts[int(account_name.removeprefix("account_"))]
        for role, account_name in profile["roles"].items()
    }
    dependencies: dict[str, str] = {}
    for dependency_id, dependency in profile.get("auxiliary_contracts", {}).items():
        dependency_artifact = compile_named_contract(
            dependency.get("source", profile["source"]),
            dependency.get("compiler", profile["compiler"]),
            dependency["contract_name"],
        )
        dependency_receipt = backend.deploy(
            dependency_artifact["bin"],
            dependency_artifact["abi"],
            dependency.get("constructor_args", []),
            roles[dependency.get("deployer_role", "owner")],
        )
        if (
            not dependency_receipt.success
            or dependency_receipt.contract_address is None
        ):
            raise RuntimeError(f"Deployment failed for dependency {dependency_id}")
        dependencies[dependency_id] = dependency_receipt.contract_address

    constructor_args = [
        _resolve_value(
            {"role": argument["role"]}
            if argument.get("value_from") == "role_address"
            else argument.get("value"),
            roles,
            dependencies,
        )
        for argument in profile["deployment"].get("constructor_args", [])
    ]
    receipt = backend.deploy(
        artifact["bin"],
        artifact["abi"],
        constructor_args,
        roles[profile["deployment"]["deployer_role"]],
    )
    if not receipt.success or receipt.contract_address is None:
        raise RuntimeError(f"Deployment failed for {profile['contract_id']}")

    deployed = DeployedProfile(
        profile=profile,
        abi=artifact["abi"],
        backend=backend,
        contract_address=receipt.contract_address,
        roles=roles,
        dependencies=dependencies,
        deployment_receipt=receipt,
    )
    if run_initialization:
        for action in profile.get("initialization", []):
            action_receipt = deployed.transact(
                action["function"],
                [
                    _resolve_value(value, roles, dependencies)
                    for value in action.get("arguments", [])
                ],
                action["caller_role"],
                action.get("value", 0),
            )
            if not action_receipt.success:
                raise RuntimeError(
                    f"Initialization action {action['function']!r} failed for "
                    f"{profile['contract_id']}"
                )
    return deployed
