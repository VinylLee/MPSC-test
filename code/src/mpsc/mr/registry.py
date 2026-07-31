"""MR template registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field

BINDING_GAP = (
    ": the supplied contract-level source/follow-up binding and Oracle "
    "record were not available; this template is not executable"
)
MALFORMED_ADDRESS_GAP = (
    f"{BINDING_GAP}; malformed-address injection is also unavailable"
)
SECOND_BACKEND_GAP = (
    f"{BINDING_GAP}; a second blockchain backend is also unavailable"
)
ROLE_SEMANTICS_GAP = f"{BINDING_GAP}; role semantics are also unresolved"


@dataclass
class MRRegistration:
    mr_id: str
    category: str
    mutable_parameters: list[str]
    source_function: str
    execution_primitive: str
    structured: bool = True
    generated: bool = False
    executable: bool = False
    oracle_available: bool = False
    current_status: str = "unsupported"
    blocking_reason: str = BINDING_GAP
    implementation_module: str = ""
    test_file: str = ""
    config: dict = field(default_factory=dict)


def _template(
    mr_id: str,
    category: str,
    mutable_parameters: list[str],
    source_function: str,
    execution_primitive: str,
    *,
    blocking_reason: str = BINDING_GAP,
) -> MRRegistration:
    """Create a structured but deliberately non-executable template."""

    return MRRegistration(
        mr_id=mr_id,
        category=category,
        mutable_parameters=mutable_parameters,
        source_function=source_function,
        execution_primitive=execution_primitive,
        blocking_reason=blocking_reason,
    )


# Complete 38-template inventory. Do not add an
# executable flag without a separately classified MRInstance
# containing the real function binding, both inputs, observers, and predicate.
MR_REGISTRY: list[MRRegistration] = [
    _template(
        "MR1.1",
        "MR1",
        ["compiler_version"],
        "contractCompiler",
        "compiler_version_transform",
    ),
    _template(
        "MR1.2",
        "MR1",
        ["compiler_version"],
        "contractCompiler",
        "compiler_version_transform",
    ),
    _template(
        "MR1.3",
        "MR1",
        ["compiler_version"],
        "contractCompiler",
        "compiler_version_transform",
    ),
    _template(
        "MR1.4",
        "MR1",
        ["compiler_version"],
        "contractCompiler",
        "compiler_version_transform",
    ),
    _template(
        "MR1.5",
        "MR1",
        ["compiler_version"],
        "contractCompiler",
        "compiler_version_transform",
    ),
    _template(
        "MR1.6",
        "MR1",
        ["compiler_version"],
        "contractCompiler",
        "compiler_version_transform",
    ),
    _template(
        "MR2.1",
        "MR2",
        ["deployer_account"],
        "contractDeploy",
        "caller_transform",
        blocking_reason=MALFORMED_ADDRESS_GAP,
    ),
    _template(
        "MR2.2",
        "MR2",
        ["deployer_account"],
        "contractDeploy",
        "caller_transform",
        blocking_reason=MALFORMED_ADDRESS_GAP,
    ),
    _template(
        "MR2.3",
        "MR2",
        ["deployer_account"],
        "contractDeploy",
        "caller_transform",
    ),
    _template(
        "MR2.4",
        "MR2",
        ["deployer_account"],
        "contractDeploy",
        "caller_transform",
    ),
    _template(
        "MR3.1",
        "MR3",
        ["deployment_environment"],
        "contractDeploy",
        "deployment_env_transform",
        blocking_reason=SECOND_BACKEND_GAP,
    ),
    _template(
        "MR3.2",
        "MR3",
        ["deployment_environment"],
        "contractFunctionCall",
        "deployment_env_transform",
        blocking_reason=SECOND_BACKEND_GAP,
    ),
    _template(
        "MR4.1",
        "MR4",
        ["gas_limit"],
        "contractDeploy",
        "gas_limit_transform",
    ),
    _template(
        "MR4.2",
        "MR4",
        ["gas_limit"],
        "contractDeploy",
        "gas_limit_transform",
    ),
    _template(
        "MR4.3",
        "MR4",
        ["gas_limit"],
        "contractDeploy",
        "gas_limit_transform",
    ),
    _template(
        "MR4.4",
        "MR4",
        ["gas_limit"],
        "contractDeploy",
        "gas_limit_transform",
    ),
    _template(
        "MR4.5",
        "MR4",
        ["gas_limit"],
        "contractDeploy",
        "gas_limit_transform",
    ),
    _template(
        "MR4.6",
        "MR4",
        ["gas_limit"],
        "contractDeploy",
        "gas_limit_transform",
    ),
    _template(
        "MR5.1",
        "MR5",
        ["to"],
        "sendCoin",
        "recipient_transform",
        blocking_reason=MALFORMED_ADDRESS_GAP,
    ),
    _template(
        "MR5.2",
        "MR5",
        ["to"],
        "sendCoin",
        "recipient_transform",
        blocking_reason=MALFORMED_ADDRESS_GAP,
    ),
    _template(
        "MR5.3", "MR5", ["to"], "sendCoin", "recipient_transform"
    ),
    _template(
        "MR5.4",
        "MR5",
        ["from", "to"],
        "sendCoin",
        "address_role_transform",
    ),
    _template(
        "MR5.5", "MR5", ["to"], "sendCoin", "recipient_transform"
    ),
    _template(
        "MR6.1", "MR6", ["amount"], "sendCoin", "amount_transform"
    ),
    _template(
        "MR6.2", "MR6", ["amount"], "sendCoin", "amount_transform"
    ),
    _template(
        "MR6.3", "MR6", ["amount"], "sendCoin", "amount_transform"
    ),
    _template(
        "MR6.4", "MR6", ["amount"], "sendCoin", "amount_transform"
    ),
    _template(
        "MR6.5", "MR6", ["amount"], "sendCoin", "amount_transform"
    ),
    _template(
        "MR6.6", "MR6", ["amount"], "sendCoin", "amount_transform"
    ),
    _template(
        "MR6.7", "MR6", ["amount"], "sendCoin", "amount_transform"
    ),
    _template(
        "MR7.1",
        "MR7",
        ["addr"],
        "getBalance",
        "query_address_transform",
        blocking_reason=MALFORMED_ADDRESS_GAP,
    ),
    _template(
        "MR7.2",
        "MR7",
        ["addr"],
        "getBalance",
        "query_address_transform",
        blocking_reason=MALFORMED_ADDRESS_GAP,
    ),
    _template(
        "MR7.3", "MR7", ["addr"], "getBalance", "query_address_transform"
    ),
    _template(
        "MR7.4", "MR7", ["addr"], "getBalance", "query_address_transform"
    ),
    _template(
        "MR8.1",
        "MR8",
        ["from", "to"],
        "sendCoin",
        "address_role_transform",
        blocking_reason=ROLE_SEMANTICS_GAP,
    ),
    _template(
        "MR8.2",
        "MR8",
        ["from", "to"],
        "sendCoin",
        "address_role_transform",
    ),
    _template(
        "MR8.3",
        "MR8",
        ["from", "to"],
        "sendCoin",
        "address_role_transform",
    ),
    _template(
        "MR9.1",
        "MR9",
        ["to", "amount"],
        "sendCoin",
        "raw_calldata_transform",
    ),
]

MR_BY_ID = {mr.mr_id: mr for mr in MR_REGISTRY}
MR_CATEGORIES = sorted({mr.category for mr in MR_REGISTRY})


def get_mrs_by_category(category: str) -> list[MRRegistration]:
    return [mr for mr in MR_REGISTRY if mr.category == category]


def get_executable_mrs() -> list[MRRegistration]:
    """Return template rows eligible for execution (currently none)."""

    return [mr for mr in MR_REGISTRY if mr.executable]


def get_supported_mrs() -> list[MRRegistration]:
    """Return template rows with execution support (none)."""

    return [mr for mr in MR_REGISTRY if mr.current_status == "supported"]


def get_templates():
    """Return the template inventory through the semantic model."""

    from .semantics import MRTemplate

    return [MRTemplate.from_registration(registration) for registration in MR_REGISTRY]
