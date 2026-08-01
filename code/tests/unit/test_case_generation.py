"""Deterministic canonical test-pair generation tests."""

import json

import pytest
from mpsc.testing.case_generation import generate_mytoken_mr6_cases

ACCOUNTS = [
    "0x0000000000000000000000000000000000000001",
    "0x0000000000000000000000000000000000000002",
]


def test_all_seven_mr6_pairs_are_generated_from_config():
    cases = generate_mytoken_mr6_cases(ACCOUNTS, seed=7)

    assert [case.template.mr_id for case in cases] == [
        "MR6.1",
        "MR6.2",
        "MR6.3",
        "MR6.4",
        "MR6.5",
        "MR6.6",
        "MR6.7",
    ]
    assert cases[0].pair.source.inputs["amount"] == 100
    assert cases[0].pair.followup.inputs["amount"] == 900
    assert all(case.pair.seed == 7 for case in cases)
    assert all(case.instance.is_semantically_complete for case in cases)


def test_same_seed_and_config_produce_identical_serialized_cases():
    first = generate_mytoken_mr6_cases(ACCOUNTS, seed=11)
    second = generate_mytoken_mr6_cases(ACCOUNTS, seed=11)

    assert [case.to_dict() for case in first] == [case.to_dict() for case in second]


def test_generated_case_writes_stable_json(tmp_path):
    generated = generate_mytoken_mr6_cases(ACCOUNTS, seed=13)[0]

    first_path = generated.write_json(tmp_path / "first.json")
    second_path = generated.write_json(tmp_path / "second.json")

    assert first_path.read_bytes() == second_path.read_bytes()
    payload = json.loads(first_path.read_text(encoding="utf-8"))
    assert payload["pair"]["source"]["inputs"]["amount"] == 100
    assert payload["pair"]["followup"]["inputs"]["amount"] == 900
    assert payload["pair"]["state_strategy"] == "fresh_deployment"
    assert payload["pair"]["seed"] == 13


def test_transform_config_mismatch_is_rejected(tmp_path):
    source = (
        "category: MR6\n"
        "description: bad fixture\n"
        "initial_state:\n"
        "  sender_balance: 10000\n"
        "  receiver_balance: 0\n"
        "mrs:\n"
        "  - id: MR6.1\n"
        "    source_amount: 100\n"
        "    transform:\n"
        "      type: subtract_from_constant\n"
        "      constant: 1000\n"
        "    followup_amount: 901\n"
        "    predicates: {}\n"
        "    constraints: []\n"
    )
    config = tmp_path / "bad.yaml"
    config.write_text(source, encoding="utf-8")

    with pytest.raises(ValueError, match="transform/config mismatch"):
        generate_mytoken_mr6_cases(ACCOUNTS, config_path=config)


def test_generation_requires_source_and_receiver_accounts():
    with pytest.raises(ValueError, match="at least two accounts"):
        generate_mytoken_mr6_cases([ACCOUNTS[0]])
