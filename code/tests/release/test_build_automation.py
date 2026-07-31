"""Release gates for the locked native build and run contract."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPT_STEMS = ("bootstrap", "run_smoke", "run_available")
SOLC_VERSIONS = ("0.4.11", "0.4.16", "0.4.19", "0.7.6")
BASE_IMAGE_DIGEST = (
    "sha256:b18992999dbe963a45a8a4da40ac2b1975be1a776d939d098c647482bcad5cba"
)


def _load_runner():
    path = Path("code/scripts/run_experiment.py").resolve()
    spec = importlib.util.spec_from_file_location("gate7_run_experiment", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_exported_repository(root: Path) -> None:
    (root / "evidence").mkdir(parents=True)
    (root / "experiment-data" / "runs").mkdir(parents=True)
    (root / "published.txt").write_text("published\n", encoding="utf-8")
    (root / "evidence" / "record.json").write_text("{}\n", encoding="utf-8")
    manifest = {
        "artifact_groups": [
            {
                "id": "published-file",
                "path": "published.txt",
                "type": "file",
            },
            {
                "id": "published-directory",
                "path": "evidence",
                "type": "directory",
            },
        ]
    }
    (root / "ARTIFACT_MANIFEST.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )


def test_machine_readable_build_contract_and_locked_export_pass():
    result = subprocess.run(
        [
            sys.executable,
            "code/scripts/verify_build_contract.py",
            "--check-export",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    assert {item["name"] for item in payload["checks"]} >= {
        "python-lock-range",
        "uv-version",
        "requirements-hash-lock",
        "requirements-export",
    }


def test_native_entrypoints_are_symmetric_strict_and_root_relative():
    for stem in SCRIPT_STEMS:
        shell = Path("scripts") / f"{stem}.sh"
        powershell = Path("scripts") / f"{stem}.ps1"
        assert shell.is_file()
        assert powershell.is_file()
        sh_text = shell.read_text(encoding="utf-8")
        ps_text = powershell.read_text(encoding="utf-8")
        assert "set -Eeuo pipefail" in sh_text
        assert "BASH_SOURCE[0]" in sh_text
        assert '$ErrorActionPreference = "Stop"' in ps_text
        assert "$PSScriptRoot" in ps_text
        if stem.startswith("run_"):
            mode = stem.removeprefix("run_")
            assert f"run_experiment.py {mode}" in sh_text
            assert f'"code/scripts/run_experiment.py", "{mode}"' in ps_text


def test_runner_rejects_output_outside_ignored_runs(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "code/scripts/run_experiment.py",
            "smoke",
            "--output",
            str(tmp_path / "forbidden"),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 2
    assert "output must be inside" in result.stderr
    assert not (tmp_path / "forbidden").exists()


def test_runner_contract_is_behavioral_in_export_without_git(tmp_path, monkeypatch):
    runner = _load_runner()
    _make_exported_repository(tmp_path)
    output = tmp_path / "experiment-data" / "runs" / "success"
    output.mkdir()
    monkeypatch.setattr(
        runner,
        "_steps",
        lambda mode, output, repo_root: [
            {
                "id": "behavioral-success",
                "evidence_class": "control",
                "command": [sys.executable, "-c", "print('ok')"],
            }
        ],
    )

    assert not (tmp_path / ".git").exists()
    assert runner.run("smoke", output, repo_root=tmp_path) == 0
    summary = json.loads((output / "run_summary.json").read_text(encoding="utf-8"))
    commands = [
        json.loads(line)
        for line in (output / "commands.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert summary["status"] == "pass"
    assert summary["published_evidence_modified"] is False
    assert summary["published_evidence_check"]["status"] == "pass"
    assert summary["provider_calls_made"] == 0
    assert summary["failure"] is None
    assert commands[0]["stage"] == "behavioral-success"
    assert (output / summary["stages"][0]["stdout_log"]).read_text(
        encoding="utf-8"
    ).strip() == "ok"


def test_snapshot_detects_changed_missing_and_unexpected_tree_state(tmp_path):
    runner = _load_runner()
    _make_exported_repository(tmp_path)
    before = runner.capture_published_evidence_snapshot(tmp_path)
    (tmp_path / "published.txt").unlink()
    (tmp_path / "evidence" / "unexpected.json").write_text(
        '{"unexpected": true}\n',
        encoding="utf-8",
    )
    after = runner.capture_published_evidence_snapshot(tmp_path)
    comparison = runner.compare_published_evidence_snapshots(before, after)

    assert after["status"] == "fail"
    assert comparison["status"] == "fail"
    assert comparison["modified"] is True
    assert {item["artifact_id"] for item in comparison["changes"]} == {
        "published-file",
        "published-directory",
    }
    assert any(item["kind"] == "missing_or_invalid" for item in comparison["changes"])
    assert any(item["kind"] == "content_changed" for item in comparison["changes"])


def test_runner_fails_and_still_summarizes_evidence_mutation(tmp_path, monkeypatch):
    runner = _load_runner()
    _make_exported_repository(tmp_path)
    output = tmp_path / "experiment-data" / "runs" / "mutation"
    output.mkdir()
    monkeypatch.setattr(
        runner,
        "_steps",
        lambda mode, output, repo_root: [
            {
                "id": "mutating-step",
                "evidence_class": "control",
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path; "
                        "Path('published.txt').write_text('changed')"
                    ),
                ],
            }
        ],
    )

    assert runner.run("smoke", output, repo_root=tmp_path) == 1
    summary = json.loads((output / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "fail"
    assert summary["published_evidence_modified"] is True
    assert summary["published_evidence_check"]["status"] == "fail"
    assert summary["failure"]["stage"] == "published-evidence-postcheck"
    assert summary["failures"]


def test_ci_uses_primary_matrix_and_never_calls_an_llm_provider():
    workflow_text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    workflow = yaml.load(workflow_text, Loader=yaml.BaseLoader)

    assert workflow["env"]["UV_VERSION"] == "0.11.29"
    assert set(workflow["jobs"]) == {
        "lint",
        "readme-entrypoints",
    }
    assert all(job["runs-on"] == "windows-2022" for job in workflow["jobs"].values())
    for command in (
        r".\scripts\bootstrap.ps1 -InstallSolc",
        r".\scripts\run_smoke.ps1",
        r".\scripts\run_available.ps1",
    ):
        assert command in workflow_text
    assert "prepare-llm" not in workflow_text
    assert "--ignore" not in workflow_text
    assert "--exclude" not in workflow_text
    assert "ruff check ." in workflow_text
    assert "--select" not in workflow_text
    assert "python -m compileall -q ." in workflow_text
    assert "--minimal" not in Path("scripts/run_smoke.ps1").read_text(encoding="utf-8")
    assert "--minimal" not in Path("scripts/run_available.ps1").read_text(
        encoding="utf-8"
    )


def test_readme_commands_and_help_contract_are_live():
    readme = Path("README.md").read_text(encoding="utf-8")
    workflow_text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    matrix = json.loads(Path("BUILD_MATRIX.json").read_text(encoding="utf-8"))

    for stem in SCRIPT_STEMS:
        assert f"scripts\\{stem}.ps1" in readme or f"{stem}.*" in readme
        assert f"scripts\\{stem}.ps1" in workflow_text
    for path in (
        Path("README.md"),
        Path("BUILD_MATRIX.json"),
        Path(".github/workflows/ci.yml"),
    ):
        text = path.read_text(encoding="utf-8").lower()
        assert not any(
            term in text
            for term in ("linux", "ubuntu", "bash scripts/", "docker", "unix")
        )
    assert "exit 0" in readme
    assert matrix["primary_environment"]["solidity_compilers"] == list(SOLC_VERSIONS)


def test_current_suite_count_and_environment_contract_cannot_drift():
    matrix = json.loads(Path("BUILD_MATRIX.json").read_text(encoding="utf-8"))
    canonical_export = (
        "uv export --locked --all-extras --no-emit-project "
        "--format requirements-txt --output-file requirements-lock.txt"
    )

    collection = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert collection.returncode == 0, collection.stdout + collection.stderr
    collected = re.search(
        r"(\d+) (?:tests|items) collected",
        collection.stdout + collection.stderr,
    )
    assert collected is not None, collection.stdout + collection.stderr
    actual_count = int(collected.group(1))

    assert actual_count == 307
    assert matrix["auxiliary_environment"]["full_suite_result"] == (
        f"{actual_count} passed"
    )
    assert matrix["lock_contract"]["requirements_export_command"] == canonical_export
    for compiler in SOLC_VERSIONS:
        assert compiler in matrix["primary_environment"]["solidity_compilers"]
    test_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("code/tests").rglob("test_*.py")
    )
    assert "pytest.mark." + "skip" not in test_source
    assert "pytest.mark." + "xfail" not in test_source


def test_bootstrap_has_read_only_and_network_install_modes():
    shell = Path("scripts/bootstrap.sh").read_text(encoding="utf-8")
    powershell = Path("scripts/bootstrap.ps1").read_text(encoding="utf-8")

    assert "--install-solc" in shell
    assert "--install-solc" in powershell
    assert "network may be required" in shell
    assert "network may be required" in powershell
    assert "doctor --project-root" in shell
    assert "doctor --project-root" in powershell


def test_shell_scripts_are_forced_lf_and_contain_no_carriage_returns():
    attributes = Path(".gitattributes").read_text(encoding="utf-8")

    assert "*.sh text eol=lf" in attributes
    for script in Path("scripts").glob("*.sh"):
        assert b"\r" not in script.read_bytes(), script


def test_build_matrix_invokes_powershell_scripts():
    matrix = json.loads(Path("BUILD_MATRIX.json").read_text(encoding="utf-8"))
    windows_commands = [
        entry["windows"]
        for entry in matrix["entry_points"]
        if entry["id"].endswith("-native")
    ]

    assert windows_commands
    assert all(command.startswith("./scripts/") for command in windows_commands)
    assert all(
        command.endswith(".ps1") or ".ps1 " in command for command in windows_commands
    )
