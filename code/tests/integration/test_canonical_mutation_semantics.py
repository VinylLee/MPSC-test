"""Positive and negative semantic controls on real MyToken mutants."""

from pathlib import Path

import pytest
from mpsc.chain.local_backend import LocalChainBackend
from mpsc.solidity.compiler import compile_contract_solcx
from mpsc.testing.canonical_executor import CanonicalExecutor
from mpsc.testing.case_generation import generate_mytoken_mr6_cases


@pytest.fixture(scope="module")
def canonical_cases():
    accounts = LocalChainBackend().get_accounts()
    return {
        case.template.mr_id: case
        for case in generate_mytoken_mr6_cases(accounts, seed=20260727)
    }


@pytest.fixture(scope="module")
def artifacts():
    paths = {
        "original": Path("experiment-data/subjects/MyToken.sol"),
        "MUT-01": Path("experiment-data/mutants/MyToken/MUT-01/MyToken.sol"),
        "MUT-08": Path("experiment-data/mutants/MyToken/MUT-08/MyToken.sol"),
    }
    compiled = {
        name: compile_contract_solcx(path, "0.4.11") for name, path in paths.items()
    }
    assert all(artifact.success for artifact in compiled.values())
    return compiled


def execute(case, artifact):
    return CanonicalExecutor().execute(
        case.template,
        case.instance,
        case.pair,
        artifact,
    )


@pytest.mark.parametrize("mr_id", ["MR6.1", "MR6.6"])
def test_original_contract_satisfies_mr_baseline(canonical_cases, artifacts, mr_id):
    result = execute(canonical_cases[mr_id], artifacts["original"])

    assert result.status == "completed"
    assert result.verdict == "pass"


@pytest.mark.parametrize("mr_id", ["MR6.1", "MR6.6"])
def test_mut_08_is_killed_by_expected_relations(canonical_cases, artifacts, mr_id):
    result = execute(canonical_cases[mr_id], artifacts["MUT-08"])

    assert result.status == "completed"
    assert result.verdict == "violation"
    assert any(
        component.status == "violated"
        for component in result.oracle_result.predicate_components
    )


def test_mut_01_is_a_real_survivor_for_mr6_1(canonical_cases, artifacts):
    result = execute(canonical_cases["MR6.1"], artifacts["MUT-01"])

    assert result.status == "completed"
    assert result.verdict == "pass"


def test_distinct_mrs_keep_distinct_inputs_and_predicates(canonical_cases):
    mr6_1 = canonical_cases["MR6.1"]
    mr6_6 = canonical_cases["MR6.6"]

    assert mr6_1.pair.followup.inputs != mr6_6.pair.followup.inputs
    assert mr6_1.pair.predicate_spec != mr6_6.pair.predicate_spec
