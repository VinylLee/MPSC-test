"""Behavior checks for initialization, roles, and observers."""

from mpsc.contracts.profile_runtime import deploy_profile


def test_mytoken_roles_transfer_and_balance_observer():
    deployed = deploy_profile("code/configs/contracts/mytoken.yaml")
    assert deployed.observe("token_balance", [deployed.roles["owner"]]) == 10_000
    receipt = deployed.transact(
        "transfer",
        [deployed.roles["user_a"], 125],
        "owner",
    )
    assert receipt.success
    assert deployed.observe("token_balance", [deployed.roles["owner"]]) == 9_875
    assert deployed.observe("token_balance", [deployed.roles["user_a"]]) == 125


def test_bectoken_constructor_owner_and_state_observers():
    deployed = deploy_profile("code/configs/contracts/bectoken.yaml")
    total_supply = deployed.observe("total_supply")
    assert deployed.observe("owner").lower() == deployed.roles["owner"].lower()
    assert deployed.observe("token_balance", [deployed.roles["owner"]]) == total_supply
    receipt = deployed.transact(
        "transfer",
        [deployed.roles["user_a"], 25],
        "owner",
    )
    assert receipt.success
    assert deployed.observe("token_balance", [deployed.roles["user_a"]]) == 25


def test_rubixi_public_initializer_can_reassign_privileged_role():
    deployed = deploy_profile("code/configs/contracts/rubixi.yaml")
    assert deployed.transact("change_fee_percentage", [7], "owner").success
    assert deployed.observe("fee_percentage")[0] == 7

    assert deployed.transact("initialize_owner", [], "user_a").success
    assert deployed.transact("change_fee_percentage", [6], "user_a").success
    assert deployed.observe("fee_percentage")[0] == 6

    assert deployed.transact("change_fee_percentage", [5], "owner").success
    assert deployed.observe("fee_percentage")[0] == 6


def test_personal_bank_initialization_and_per_user_balance_observer():
    deployed = deploy_profile("code/configs/contracts/personal_bank.yaml")
    assert deployed.observe("minimum_deposit") == 1
    assert deployed.transact("deposit", [], "user_a", value=100).success
    assert deployed.observe("bank_balance", [deployed.roles["user_a"]]) == 100
    assert deployed.observe("bank_balance", [deployed.roles["user_b"]]) == 0

    locked = deployed.transact("set_minimum", [2], "user_b")
    assert not locked.success
    assert deployed.observe("minimum_deposit") == 1


def test_gnosis_constructor_binding_and_raw_selector_observer():
    deployed = deploy_profile("code/configs/contracts/gnosissafeproxy.yaml")
    observed = deployed.observe("singleton")
    assert observed.lower() == deployed.roles["singleton"].lower()
