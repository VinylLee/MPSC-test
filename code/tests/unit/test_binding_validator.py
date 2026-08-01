"""Strict ABI and semantic binding validation tests."""

from __future__ import annotations

from copy import deepcopy

from mpsc.mr import MRInstance, validate_binding

MYTOKEN_ABI = [
    {
        "type": "function",
        "name": "sendCoin",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "_receiver", "type": "address"},
            {"name": "_amount", "type": "uint256"},
        ],
        "outputs": [{"name": "sufficient", "type": "bool"}],
    },
    {
        "type": "function",
        "name": "getBalance",
        "stateMutability": "view",
        "inputs": [{"name": "_addr", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]

ACCOUNT_1 = "0x1111111111111111111111111111111111111111"


def valid_instance() -> MRInstance:
    return MRInstance(
        instance_id="mytoken.MR6.1.sendCoin.v01",
        template_id="MR6.1",
        contract_id="mytoken",
        function="sendCoin",
        parameter_bindings={"_receiver": "address", "_amount": "uint256"},
        source_input={"_receiver": ACCOUNT_1, "_amount": 100},
        transformation={"name": "subtract_from_constant", "constant": 1000},
        followup_input={"_receiver": ACCOUNT_1, "_amount": 900},
        observers=("return_value", "contract_state.token_balances"),
        predicates=("mr6_amount",),
        predicate_spec={"mu": "mu_f == mu_s"},
        evidence_sources=("mpsc.registry:MR6.1",),
        status="resolved",
    )


def issue_codes(result) -> set[str]:
    return {issue.code for issue in result.issues}


def test_complete_binding_is_valid():
    result = validate_binding(valid_instance(), MYTOKEN_ABI)

    assert result.status == "valid"
    assert result.valid is True
    assert result.issues == []


def test_function_must_exist_in_abi():
    instance = valid_instance()
    instance.function = "notAFunction"

    result = validate_binding(instance, MYTOKEN_ABI)

    assert result.status == "invalid_binding"
    assert "function_not_in_abi" in issue_codes(result)


def test_parameter_names_and_declared_types_must_match_abi():
    instance = valid_instance()
    instance.parameter_bindings = {
        "_receiver": "uint256",
        "invented": "uint256",
    }

    result = validate_binding(instance, MYTOKEN_ABI)

    assert result.status == "invalid_binding"
    assert {
        "missing_parameter_binding",
        "extra_parameter_binding",
        "parameter_type_mismatch",
    }.issubset(issue_codes(result))


def test_source_and_followup_values_must_match_abi_types():
    instance = valid_instance()
    instance.source_input["_amount"] = -1
    instance.followup_input["_receiver"] = 123

    result = validate_binding(instance, MYTOKEN_ABI)

    assert result.status == "invalid_binding"
    assert "test_input_type_mismatch" in issue_codes(result)


def test_unknown_observer_is_unsupported_not_pass():
    instance = valid_instance()
    instance.observers = ("made_up_observer",)

    result = validate_binding(instance, MYTOKEN_ABI)

    assert result.status == "unsupported"
    assert "observer_not_implemented" in issue_codes(result)
    assert result.status != "pass"


def test_unknown_transform_is_unsupported_not_pass():
    instance = valid_instance()
    instance.transformation = {"name": "made_up_transform"}

    result = validate_binding(instance, MYTOKEN_ABI)

    assert result.status == "unsupported"
    assert "transform_not_implemented" in issue_codes(result)


def test_unknown_required_predicate_is_unsupported_not_pass():
    instance = valid_instance()
    instance.predicates = ("always_true",)

    result = validate_binding(instance, MYTOKEN_ABI)

    assert result.status == "unsupported"
    assert "predicate_not_implemented" in issue_codes(result)


def test_missing_semantic_fields_are_unsupported():
    instance = valid_instance()
    instance.observers = ()
    instance.predicates = ()
    instance.evidence_sources = ()

    result = validate_binding(instance, MYTOKEN_ABI)

    assert result.status == "unsupported"
    assert {
        "missing_observer",
        "missing_predicate",
        "incomplete_semantic_binding",
    }.issubset(issue_codes(result))


def test_instance_convenience_method_uses_same_validator():
    instance = deepcopy(valid_instance())

    result = instance.validate_binding(MYTOKEN_ABI)

    assert result.status == "valid"
