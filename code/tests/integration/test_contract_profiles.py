"""Compile every subject profile and validate it against the exact ABI."""

from __future__ import annotations

from pathlib import Path

import pytest
from mpsc.contracts.profile import (
    compile_profile_abi,
    load_contract_profile,
    validate_profile_abi,
)

PROFILE_PATHS = sorted(Path("code/configs/contracts").glob("*.yaml"))


@pytest.mark.parametrize("profile_path", PROFILE_PATHS, ids=lambda path: path.stem)
def test_contract_profile_matches_compiled_abi(profile_path: Path):
    profile = load_contract_profile(profile_path)
    abi = compile_profile_abi(profile)
    assert validate_profile_abi(profile, abi) == []


def test_all_five_supplied_subjects_have_abi_verified_profiles():
    profiles = [load_contract_profile(path) for path in PROFILE_PATHS]
    assert {profile["contract_id"] for profile in profiles} == {
        "mytoken",
        "rubixi",
        "bectoken",
        "gnosissafeproxy",
        "personal_bank",
    }
    assert all(profile["profile_status"] == "abi_verified" for profile in profiles)


def test_previously_invented_function_names_are_absent():
    rubixi = load_contract_profile("code/configs/contracts/rubixi.yaml")
    personal_bank = load_contract_profile("code/configs/contracts/personal_bank.yaml")
    solidity_names = {
        function.get("solidity_name")
        for profile in (rubixi, personal_bank)
        for function in profile["functions"].values()
    }
    assert {"create", "payout", "get_balance", "cash"} & solidity_names == set()
    assert {"DynamicPyramid", "Deposit", "Collect", "balances"} <= solidity_names
