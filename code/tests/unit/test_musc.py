"""Tests for the explicitly non-exact MuSC compatibility layer."""

import json
from pathlib import Path

from mpsc.mutation.musc import (
    OPERATOR_SETS,
    OPERATORS,
    apply_candidate,
    find_candidates,
)

FIXTURES = {
    "ROR": "if (a >= b) { x = 1; }\n",
    "LOR": "if (!flag) { x = 1; }\n",
    "COR": "if (a && b) { x = 1; }\n",
    "ASR": "balance += amount;\n",
    "SDL": "balance = amount;\n",
    "RSD": "require(amount > 0);\n",
    "RVR": "return true;\n",
    "VTR": "uint256 amount;\n",
    "DLR": "bytes memory payload;\n",
    "EUR": "uint amount = 1 ether;\n",
    "FVC": "function f() public {}\n",
    "AVR": "address actor = msg.sender;\n",
    "GVC": "uint height = block.number;\n",
    "FSC": "function f() public view returns (uint) {}\n",
    "MFR": "return addmod(a, b, n);\n",
    "PKD": "function f() public payable {}\n",
}


def test_all_16_operators_have_deterministic_generators():
    assert set(OPERATORS) == set(FIXTURES)
    for operator_id, source in FIXTURES.items():
        candidates = find_candidates(source, operator_id)
        assert candidates
        mutant = apply_candidate(source, candidates[0])
        assert mutant != source
        assert find_candidates(source, operator_id) == candidates


def test_per_contract_operator_sets_are_covered():
    assert len(OPERATOR_SETS) == 5
    assert set(OPERATOR_SETS["mytoken"]) == {
        "ROR",
        "ASR",
        "SDL",
        "VTR",
        "GVC",
        "AVR",
    }
    assert all(
        set(operator_set) <= set(OPERATORS)
        for operator_set in OPERATOR_SETS.values()
    )


def test_comments_are_not_mutated():
    assert find_candidates("// msg.sender && block.number\n", "AVR") == []
    assert find_candidates("// msg.sender && block.number\n", "COR") == []
    assert find_candidates("// msg.sender && block.number\n", "GVC") == []


def test_operator_pipeline_status_is_complete():
    from mpsc.mutation.operator_pipeline import get_operator_pipeline_status

    status = get_operator_pipeline_status()
    assert len(status) == 16
    assert all(row["generator_implemented"] for row in status)


def test_frozen_five_contract_candidate_counts_are_computed():
    paths = {
        "mytoken": "experiment-data/subjects/MyToken.sol",
        "rubixi": "experiment-data/subjects/Rubixi/Rubixi.sol",
        "bectoken": "experiment-data/subjects/BecToken/BecToken.sol",
        "gnosissafeproxy": (
            "experiment-data/subjects/GnosisSafeProxy/GnosisSafeProxy.sol"
        ),
        "personal_bank": "experiment-data/subjects/PERSONAL_BANK/PERSONAL_BANK.sol",
    }
    expected = json.loads(
        Path(
            "experiment-data/results/canonical/musc_compatibility/operator_coverage.json"
        ).read_text(encoding="utf-8")
    )
    actual = {
        contract_id: {
            operator_id: len(find_candidates(source, operator_id))
            for operator_id in OPERATOR_SETS[contract_id]
        }
        for contract_id, source_path in paths.items()
        for source in [Path(source_path).read_text(encoding="utf-8")]
    }
    assert actual == expected["contracts"]
