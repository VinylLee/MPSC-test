"""Contract-profile loading, exact compilation, and ABI validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_contract_profile(path: str | Path) -> dict[str, Any]:
    """Load a contract profile."""

    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def compile_profile_contract(
    profile: dict[str, Any],
    output_values: tuple[str, ...] = ("abi", "bin"),
) -> dict[str, Any]:
    """Compile and return the exact contract selected by the profile."""

    return compile_named_contract(
        profile["source"],
        profile["compiler"],
        profile["contract_name"],
        output_values,
    )


def compile_named_contract(
    source_path: str | Path,
    compiler: str,
    contract_name: str,
    output_values: tuple[str, ...] = ("abi", "bin"),
) -> dict[str, Any]:
    """Compile one exact named contract from a possibly multi-contract source."""

    from solcx import compile_source, set_solc_version

    set_solc_version(compiler)
    source = Path(source_path).read_text(encoding="utf-8")
    compiled = compile_source(source, output_values=list(output_values))
    expected_suffix = f":{contract_name}"
    matches = [
        value for key, value in compiled.items() if key.endswith(expected_suffix)
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one compiled {contract_name}, found {len(matches)}"
        )
    return matches[0]


def compile_profile_abi(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Compile and return the ABI for the profile's exact contract name."""

    return compile_profile_contract(profile, ("abi",))["abi"]


def _abi_mutability(item: dict[str, Any]) -> str:
    if "stateMutability" in item:
        return str(item["stateMutability"])
    if item.get("constant"):
        return "view"
    return "payable" if item.get("payable") else "nonpayable"


def _parameter_pairs(parameters: list[dict[str, str]]) -> list[tuple[str, str]]:
    return [(parameter["name"], parameter["type"]) for parameter in parameters]


def validate_profile_abi(
    profile: dict[str, Any], abi: list[dict[str, Any]]
) -> list[str]:
    """Return all profile/ABI mismatches without silently accepting aliases."""

    issues: list[str] = []
    abi_functions = {
        item["name"]: item
        for item in abi
        if item.get("type") == "function" and "name" in item
    }
    fallbacks = [item for item in abi if item.get("type") == "fallback"]
    constructors = [item for item in abi if item.get("type") == "constructor"]
    configured_names: list[str] = []
    configured_fallbacks = 0

    for alias, function in profile.get("functions", {}).items():
        abi_type = function.get("abi_type", "function")
        if abi_type == "fallback":
            configured_fallbacks += 1
            if len(fallbacks) != 1:
                issues.append(
                    f"{alias}: expected one ABI fallback, found {len(fallbacks)}"
                )
                continue
            abi_item = fallbacks[0]
        elif abi_type == "function":
            solidity_name = function.get("solidity_name")
            configured_names.append(solidity_name)
            abi_item = abi_functions.get(solidity_name)
            if abi_item is None:
                issues.append(f"{alias}: ABI function {solidity_name!r} is absent")
                continue
        else:
            issues.append(f"{alias}: unsupported abi_type {abi_type!r}")
            continue

        expected_mutability = function.get("mutability")
        actual_mutability = _abi_mutability(abi_item)
        if expected_mutability != actual_mutability:
            issues.append(
                f"{alias}: mutability {expected_mutability!r} != {actual_mutability!r}"
            )

        expected_parameters = _parameter_pairs(function.get("parameters", []))
        actual_parameters = [
            (parameter.get("name", ""), parameter["type"])
            for parameter in abi_item.get("inputs", [])
        ]
        if expected_parameters != actual_parameters:
            issues.append(
                f"{alias}: parameters {expected_parameters!r} != {actual_parameters!r}"
            )

    if len(configured_names) != len(set(configured_names)):
        issues.append("ABI functions must not be configured more than once")
    missing_functions = set(abi_functions) - set(configured_names)
    if missing_functions:
        issues.append(f"unconfigured ABI functions: {sorted(missing_functions)!r}")
    if fallbacks and configured_fallbacks != 1:
        issues.append(
            "ABI fallback must be configured exactly once, "
            f"found {configured_fallbacks}"
        )

    constructor_inputs = (
        constructors[0].get("inputs", []) if len(constructors) == 1 else []
    )
    expected_constructor = _parameter_pairs(
        profile.get("deployment", {}).get("constructor_args", [])
    )
    actual_constructor = [
        (parameter.get("name", ""), parameter["type"])
        for parameter in constructor_inputs
    ]
    if expected_constructor != actual_constructor:
        issues.append(
            f"constructor parameters {expected_constructor!r} != {actual_constructor!r}"
        )

    for observer in profile.get("state_observers", []):
        function_alias = observer["function"]
        function = profile.get("functions", {}).get(function_alias)
        if function is None:
            issues.append(
                f"observer {observer['id']}: function alias "
                f"{function_alias!r} is absent"
            )
            continue

        if observer.get("kind", "function") == "raw_selector":
            if function.get("abi_type") != "fallback":
                issues.append(
                    f"observer {observer['id']}: raw selector requires ABI fallback"
                )
            from eth_utils import keccak

            expected = "0x" + keccak(text=observer["signature"])[:4].hex()
            if observer.get("selector") != expected:
                issues.append(
                    f"observer {observer['id']}: selector "
                    f"{observer.get('selector')!r} != {expected!r}"
                )
            continue

        if function.get("mutability") not in {"view", "pure"}:
            issues.append(
                f"observer {observer['id']}: {function_alias!r} is not read-only"
            )
        if len(observer.get("arguments", [])) != len(function.get("parameters", [])):
            issues.append(
                f"observer {observer['id']}: argument count does not match "
                f"{function_alias!r}"
            )

    roles = profile.get("roles", {})
    for action in profile.get("initialization", []):
        alias = action["function"]
        function = profile.get("functions", {}).get(alias)
        if function is None:
            issues.append(f"initialization: function alias {alias!r} is absent")
            continue
        if function.get("abi_type", "function") != "function":
            issues.append(f"initialization: {alias!r} is not an ABI function")
        if function.get("mutability") in {"view", "pure"}:
            issues.append(f"initialization: {alias!r} is read-only")
        if len(action.get("arguments", [])) != len(function.get("parameters", [])):
            issues.append(f"initialization: argument count does not match {alias!r}")
        if action.get("caller_role") not in roles:
            issues.append(
                f"initialization: caller role {action.get('caller_role')!r} is absent"
            )

    if profile.get("mr_binding_status") != ("verified_without_instance_records"):
        issues.append("MR binding evidence status must be explicit")

    return issues
