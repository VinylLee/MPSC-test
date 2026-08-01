"""Release gates for the MPSC implementation boundary."""

from __future__ import annotations

from pathlib import Path

import yaml
from mpsc.mr.registry import (
    MR_REGISTRY,
    get_executable_mrs,
    get_supported_mrs,
)


def test_all_38_template_registrations_are_structured_but_fail_closed():
    assert len(MR_REGISTRY) == 38
    assert get_executable_mrs() == []
    assert get_supported_mrs() == []
    for registration in MR_REGISTRY:
        assert registration.structured is True
        assert registration.executable is False
        assert registration.oracle_available is False
        assert registration.current_status == "unsupported"
        assert registration.implementation_module == ""
        assert "not available" in registration.blocking_reason


def test_public_catalog_never_marks_a_registry_template_executable():
    catalog = yaml.safe_load(
        Path("experiment-data/specification/mr_catalog.yaml").read_text(
            encoding="utf-8"
        )
    )

    assert len(catalog["mrs"]) == 38
    for template in catalog["mrs"]:
        assert template["automation"]["executable"] is False
        assert template["automation"]["missing_information"]


def test_supported_reference_control_modules_and_inputs_exist():
    required = (
        "code/src/mpsc/testing/case_generation.py",
        "code/src/mpsc/testing/canonical_executor.py",
        "code/src/mpsc/testing/oracle.py",
        "code/src/mpsc/experiments/canonical_matrix.py",
        "code/configs/mrs/mr6.yaml",
        "code/configs/experiments/mytoken_canonical_mutants.yaml",
        "experiment-data/subjects/MyToken.sol",
    )

    missing = [path for path in required if not Path(path).is_file()]
    assert not missing
