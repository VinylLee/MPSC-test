from __future__ import annotations

import json

from click.testing import CliRunner
from mpsc.cli import main
from mpsc.doctor import _compiler_probe, run_doctor


def test_doctor_runs_real_compile_deploy_and_input_checks():
    result = run_doctor()

    assert result["status"] == "pass"
    assert [item["name"] for item in result["checks"]] == [
        "python",
        "run-inputs",
        "locked-build-contract",
        "artifact-manifest",
        "frozen-mutant-corpus",
        "solc-0.4.11",
        "solc-0.4.16",
        "solc-0.4.19",
        "solc-0.7.6",
        "local-evm",
    ]
    assert all(item["status"] == "pass" for item in result["checks"])
    local_evm = next(item for item in result["checks"] if item["name"] == "local-evm")
    assert "ping=1" in local_evm["detail"]


def test_doctor_json_cli_is_machine_readable():
    result = CliRunner().invoke(main, ["doctor", "--json-output"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "pass"
    assert payload["schema_version"] == 1
    assert payload["network_may_be_required"] is False
    assert all(item["status"] == "pass" for item in payload["checks"])


def test_doctor_fails_when_checkout_inputs_are_missing(tmp_path):
    result = run_doctor(project_root=tmp_path)

    assert result["status"] == "fail"
    input_check = next(
        item for item in result["checks"] if item["name"] == "run-inputs"
    )
    assert input_check["status"] == "fail"
    assert "experiment-data/processed/normalized_manifest.json" in input_check["detail"]


def test_doctor_missing_compiler_fails_with_network_remediation(monkeypatch):
    import solcx

    monkeypatch.setattr(solcx, "get_installed_solc_versions", lambda: [])
    check, artifact = _compiler_probe("0.4.11", install_solc=False)

    assert artifact is None
    assert check.status == "fail"
    assert check.detail == "compiler is not installed"
    assert "network access" in (check.remediation or "")
