"""Strict validation for binding an MR instance to a contract ABI."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

from .semantics import MRInstance

SUPPORTED_TRANSFORMS = frozenset(
    {
        "compiler_version_transform",
        "caller_transform",
        "gas_limit_transform",
        "recipient_transform",
        "amount_transform",
        "subtract_from_constant",
        "add_constant",
        "multiply_constant",
        "power_minus_source",
        "power_plus_source",
        "query_address_transform",
        "address_role_transform",
        "raw_calldata_transform",
    }
)

SUPPORTED_OBSERVERS = frozenset(
    {
        "execution_status",
        "return_value",
        "transaction.receipt_status",
        "transaction.gas_used",
        "native_balances",
        "contract_state",
        "contract_state.token_balances",
        "events",
    }
)

SUPPORTED_PREDICATES = frozenset(
    {
        "view_different_return",
        "state_change_balance",
        "parameter_swap_raw",
        "state_change_full",
        "mr6_amount",
    }
)

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_BYTES_RE = re.compile(r"^bytes(?P<size>[1-9]|[12][0-9]|3[0-2])$")
_INT_RE = re.compile(r"^(?P<unsigned>u?)int(?P<bits>[0-9]{0,3})$")
_ARRAY_RE = re.compile(r"^(?P<base>.+)\[(?P<size>[0-9]*)\]$")


@dataclass(frozen=True)
class BindingIssue:
    code: str
    field: str
    message: str


@dataclass
class BindingValidationResult:
    status: Literal["valid", "invalid_binding", "unsupported"]
    issues: list[BindingIssue] = field(default_factory=list)
    abi_function: dict[str, Any] | None = None

    @property
    def valid(self) -> bool:
        return self.status == "valid"


def validate_binding(
    instance: MRInstance,
    abi: list[dict[str, Any]],
    *,
    available_observers: Iterable[str] = SUPPORTED_OBSERVERS,
    available_transforms: Iterable[str] = SUPPORTED_TRANSFORMS,
    available_predicates: Iterable[str] = SUPPORTED_PREDICATES,
) -> BindingValidationResult:
    """Validate an instance without executing it.

    ABI mismatches are ``invalid_binding``. Missing semantic implementations
    are ``unsupported``. This function never returns an MR test verdict.
    """

    invalid: list[BindingIssue] = []
    unsupported: list[BindingIssue] = []
    is_constructor = instance.function in {"constructor", "contractDeploy"}
    functions = [
        entry
        for entry in abi
        if (
            is_constructor
            and entry.get("type") == "constructor"
            or entry.get("type") == "function"
            and entry.get("name") == instance.function
        )
    ]
    if is_constructor and not functions:
        functions = [{"type": "constructor", "inputs": []}]

    if not functions:
        invalid.append(
            BindingIssue(
                "function_not_in_abi",
                "function",
                f"{instance.function!r} does not exist in the contract ABI",
            )
        )
        return BindingValidationResult("invalid_binding", invalid)

    abi_function = _select_overload(instance, functions)
    if abi_function is None:
        invalid.append(
            BindingIssue(
                "ambiguous_or_unmatched_overload",
                "parameter_bindings",
                f"no overload of {instance.function!r} matches the declared binding",
            )
        )
        return BindingValidationResult("invalid_binding", invalid)

    inputs = abi_function.get("inputs", [])
    abi_parameters = {entry.get("name", ""): entry.get("type", "") for entry in inputs}
    binding_parameters = set(instance.parameter_bindings)
    expected_parameters = set(abi_parameters)

    missing = sorted(expected_parameters - binding_parameters)
    extra = sorted(binding_parameters - expected_parameters)
    if missing:
        invalid.append(
            BindingIssue(
                "missing_parameter_binding",
                "parameter_bindings",
                f"missing ABI parameters: {', '.join(missing)}",
            )
        )
    if extra:
        invalid.append(
            BindingIssue(
                "extra_parameter_binding",
                "parameter_bindings",
                f"parameters not present in ABI: {', '.join(extra)}",
            )
        )

    for name, abi_type in abi_parameters.items():
        declared_type = _declared_abi_type(instance.parameter_bindings.get(name))
        if declared_type is not None and declared_type != abi_type:
            invalid.append(
                BindingIssue(
                    "parameter_type_mismatch",
                    f"parameter_bindings.{name}",
                    f"declared {declared_type!r}, ABI requires {abi_type!r}",
                )
            )

    _validate_case_inputs(
        instance.source_input, abi_parameters, "source_input", invalid
    )
    _validate_case_inputs(
        instance.followup_input, abi_parameters, "followup_input", invalid
    )

    transform_name = instance.transformation.get("name") or instance.transformation.get(
        "type"
    )
    if not transform_name:
        unsupported.append(
            BindingIssue(
                "missing_transform",
                "transformation",
                "no source-to-follow-up transform is declared",
            )
        )
    elif transform_name not in set(available_transforms):
        unsupported.append(
            BindingIssue(
                "transform_not_implemented",
                "transformation",
                f"transform {transform_name!r} has no registered implementation",
            )
        )

    observer_registry = set(available_observers)
    if not instance.observers:
        unsupported.append(
            BindingIssue(
                "missing_observer",
                "observers",
                "at least one executable observer is required",
            )
        )
    for observer in instance.observers:
        if observer not in observer_registry:
            unsupported.append(
                BindingIssue(
                    "observer_not_implemented",
                    "observers",
                    f"observer {observer!r} has no registered implementation",
                )
            )

    predicate_registry = set(available_predicates)
    if not instance.predicates:
        unsupported.append(
            BindingIssue(
                "missing_predicate",
                "predicates",
                "at least one required predicate implementation is required",
            )
        )
    for predicate in instance.predicates:
        if predicate not in predicate_registry:
            unsupported.append(
                BindingIssue(
                    "predicate_not_implemented",
                    "predicates",
                    f"required predicate {predicate!r} has no registered "
                    "implementation",
                )
            )

    for gap in instance.semantic_gaps():
        if gap not in {"transformation", "observers", "predicates"}:
            unsupported.append(
                BindingIssue(
                    "incomplete_semantic_binding",
                    gap,
                    f"required semantic field {gap!r} is missing",
                )
            )

    if invalid:
        return BindingValidationResult(
            "invalid_binding", invalid + unsupported, abi_function
        )
    if unsupported:
        return BindingValidationResult("unsupported", unsupported, abi_function)
    return BindingValidationResult("valid", abi_function=abi_function)


def _select_overload(
    instance: MRInstance, functions: list[dict[str, Any]]
) -> dict[str, Any] | None:
    if len(functions) == 1:
        return functions[0]

    matches: list[dict[str, Any]] = []
    for function in functions:
        inputs = function.get("inputs", [])
        if set(instance.parameter_bindings) != {
            entry.get("name", "") for entry in inputs
        }:
            continue
        if all(
            _declared_abi_type(instance.parameter_bindings.get(entry.get("name", "")))
            in {None, entry.get("type")}
            for entry in inputs
        ):
            matches.append(function)
    return matches[0] if len(matches) == 1 else None


def _declared_abi_type(binding: Any) -> str | None:
    if isinstance(binding, str):
        return binding
    if isinstance(binding, dict):
        value = binding.get("abi_type")
        return value if isinstance(value, str) else None
    return None


def _validate_case_inputs(
    values: dict[str, Any],
    abi_parameters: dict[str, str],
    field_name: str,
    issues: list[BindingIssue],
) -> None:
    missing = sorted(set(abi_parameters) - set(values))
    extra = sorted(set(values) - set(abi_parameters))
    if missing:
        issues.append(
            BindingIssue(
                "missing_test_input",
                field_name,
                f"missing ABI inputs: {', '.join(missing)}",
            )
        )
    if extra:
        issues.append(
            BindingIssue(
                "extra_test_input",
                field_name,
                f"inputs not present in ABI: {', '.join(extra)}",
            )
        )
    for name, abi_type in abi_parameters.items():
        if name in values and not _matches_abi_type(values[name], abi_type):
            issues.append(
                BindingIssue(
                    "test_input_type_mismatch",
                    f"{field_name}.{name}",
                    f"value {values[name]!r} is not compatible with {abi_type}",
                )
            )


def _matches_abi_type(value: Any, abi_type: str) -> bool:
    array_match = _ARRAY_RE.fullmatch(abi_type)
    if array_match:
        if not isinstance(value, (list, tuple)):
            return False
        size = array_match.group("size")
        if size and len(value) != int(size):
            return False
        return all(_matches_abi_type(item, array_match.group("base")) for item in value)

    int_match = _INT_RE.fullmatch(abi_type)
    if int_match:
        if isinstance(value, bool) or not isinstance(value, int):
            return False
        if int_match.group("unsigned") and value < 0:
            return False
        bits_text = int_match.group("bits")
        bits = int(bits_text) if bits_text else 256
        if bits < 8 or bits > 256 or bits % 8:
            return False
        if int_match.group("unsigned"):
            return value < 2**bits
        return -(2 ** (bits - 1)) <= value < 2 ** (bits - 1)

    if abi_type == "address":
        return isinstance(value, str) and bool(_ADDRESS_RE.fullmatch(value))
    if abi_type == "bool":
        return isinstance(value, bool)
    if abi_type == "string":
        return isinstance(value, str)
    if abi_type == "bytes":
        return isinstance(value, (bytes, bytearray, str))

    bytes_match = _BYTES_RE.fullmatch(abi_type)
    if bytes_match:
        size = int(bytes_match.group("size"))
        if isinstance(value, (bytes, bytearray)):
            return len(value) == size
        if isinstance(value, str) and value.startswith("0x"):
            return len(value) == 2 + size * 2
        return False
    return False
