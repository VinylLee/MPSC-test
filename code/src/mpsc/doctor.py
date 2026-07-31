"""Executable environment preflight for the MPSC run package."""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SOLC_VERSIONS = ("0.4.11", "0.4.16", "0.4.19", "0.7.6")
REQUIRED_INPUTS = (
    "ARTIFACT_MANIFEST.json",
    "BUILD_MATRIX.json",
    ".python-version",
    "pyproject.toml",
    "uv.lock",
    "requirements-lock.txt",
    "experiment-data/subjects/MyToken.sol",
    "code/configs/experiments/mytoken_canonical_mutants.yaml",
    "experiment-data/processed/normalized_manifest.json",
    "experiment-data/specification/mr_catalog.yaml",
)


@dataclass(frozen=True)
class DoctorCheck:
    """One independently actionable preflight check."""

    name: str
    status: str
    detail: str
    remediation: str | None = None


def _python_check() -> DoctorCheck:
    supported = (3, 11) <= sys.version_info[:2] < (3, 14)
    return DoctorCheck(
        name="python",
        status="pass" if supported else "fail",
        detail=f"{platform.python_implementation()} {platform.python_version()}",
        remediation=(
            None
            if supported
            else "Use CPython 3.11, 3.12, or 3.13 and reinstall from uv.lock."
        ),
    )


def _input_check(project_root: Path) -> DoctorCheck:
    missing = [path for path in REQUIRED_INPUTS if not (project_root / path).is_file()]
    if missing:
        return DoctorCheck(
            name="run-inputs",
            status="fail",
            detail="missing: " + ", ".join(missing),
            remediation="Run doctor from a complete checkout of the MPSC repository.",
        )
    return DoctorCheck(
        name="run-inputs",
        status="pass",
        detail=f"{len(REQUIRED_INPUTS)} required public run inputs found",
    )


def _corpus_check(project_root: Path) -> DoctorCheck:
    from .mutation.corpus import validate_frozen_corpus

    try:
        report = validate_frozen_corpus(
            project_root / "code/configs/experiments/mytoken_canonical_mutants.yaml",
            base_dir=project_root,
        )
    except Exception as error:
        return DoctorCheck(
            name="frozen-mutant-corpus",
            status="fail",
            detail=f"{type(error).__name__}: {error}",
            remediation=(
                "Restore the tracked canonical subject, mutants, and manifests."
            ),
        )
    passed = (
        report["subject"]["frozen_hash_matches"]
        and report["eligible_count"] == report["mutant_count"]
    )
    return DoctorCheck(
        name="frozen-mutant-corpus",
        status="pass" if passed else "fail",
        detail=(
            f"{report['eligible_count']}/{report['mutant_count']} eligible; "
            f"subject_hash_match={report['subject']['frozen_hash_matches']}"
        ),
        remediation=(
            None
            if passed
            else "Do not run canonical experiments until corpus hashes are restored."
        ),
    )


def _script_json_check(
    project_root: Path,
    *,
    name: str,
    script: str,
    remediation: str,
) -> DoctorCheck:
    path = project_root / script
    if not path.is_file():
        return DoctorCheck(
            name=name,
            status="fail",
            detail=f"missing validator: {script}",
            remediation=remediation,
        )
    result = subprocess.run(
        [sys.executable, str(path)],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {}
    passed = result.returncode == 0 and payload.get("status") == "pass"
    detail = (
        f"{script}: status=pass"
        if passed
        else (result.stdout + result.stderr).strip()[-1000:]
    )
    return DoctorCheck(
        name=name,
        status="pass" if passed else "fail",
        detail=detail,
        remediation=None if passed else remediation,
    )


def _compiler_probe(
    version: str,
    install_solc: bool,
) -> tuple[DoctorCheck, dict[str, Any] | None]:
    try:
        import solcx
    except Exception as error:
        return (
            DoctorCheck(
                name=f"solc-{version}",
                status="fail",
                detail=f"py-solc-x import failed: {error}",
                remediation="Install the locked project dependencies.",
            ),
            None,
        )

    installed = {str(version) for version in solcx.get_installed_solc_versions()}
    if version not in installed:
        if not install_solc:
            return (
                DoctorCheck(
                    name=f"solc-{version}",
                    status="fail",
                    detail="compiler is not installed",
                    remediation=(
                        "Run `mpsc doctor --install-solc` once with network access."
                    ),
                ),
                None,
            )
        try:
            solcx.install_solc(version)
        except Exception as error:
            return (
                DoctorCheck(
                    name=f"solc-{version}",
                    status="fail",
                    detail=f"installation failed: {type(error).__name__}: {error}",
                    remediation=(
                        "Check network/proxy access to the Solidity binary mirror."
                    ),
                ),
                None,
            )

    source = (
        f"""
      pragma solidity {version};
      contract DoctorProbe {{
        function ping() constant returns (uint256) {{ return 1; }}
      }}
    """
        if version.startswith("0.4.")
        else f"""
      pragma solidity {version};
      contract DoctorProbe {{
        function ping() external pure returns (uint256) {{ return 1; }}
      }}
    """
    )
    try:
        solcx.set_solc_version(version)
        compiled = solcx.compile_source(source, output_values=["abi", "bin"])
        artifact = next(iter(compiled.values()))
    except Exception as error:
        return (
            DoctorCheck(
                name=f"solc-{version}",
                status="fail",
                detail=f"compile probe failed: {type(error).__name__}: {error}",
                remediation=(
                    "Remove the broken solc installation and rerun with --install-solc."
                ),
            ),
            None,
        )
    return (
        DoctorCheck(
            name=f"solc-{version}",
            status="pass",
            detail="installed and compiled DoctorProbe",
        ),
        artifact,
    )


def _local_chain_probe(artifact: dict[str, Any] | None) -> DoctorCheck:
    if artifact is None:
        return DoctorCheck(
            name="local-evm",
            status="fail",
            detail="not attempted because the compiler probe failed",
            remediation="Fix the solc check first, then rerun doctor.",
        )
    try:
        from .chain.local_backend import LocalChainBackend

        backend = LocalChainBackend()
        accounts = backend.get_accounts()
        receipt = backend.deploy(artifact["bin"], artifact["abi"])
        value = backend.call_view(
            receipt.contract_address or "",
            artifact["abi"],
            "ping",
        )
        passed = len(accounts) >= 2 and receipt.success and value == 1
        detail = f"accounts={len(accounts)}, deploy={receipt.success}, ping={value}"
    except Exception as error:
        return DoctorCheck(
            name="local-evm",
            status="fail",
            detail=f"{type(error).__name__}: {error}",
            remediation=(
                "Reinstall the locked web3, eth-tester, and py-evm dependencies."
            ),
        )
    return DoctorCheck(
        name="local-evm",
        status="pass" if passed else "fail",
        detail=detail,
        remediation=None if passed else "Inspect the local PyEVM installation.",
    )


def run_doctor(
    *,
    project_root: str | Path = ".",
    install_solc: bool = False,
    runtime_only: bool = False,
) -> dict[str, Any]:
    """Run all preflight checks and return a stable machine-readable result."""

    root = Path(project_root).resolve()
    compiler_probes = [
        _compiler_probe(version, install_solc) for version in SOLC_VERSIONS
    ]
    artifact = compiler_probes[0][1]
    runtime_checks = [
        _python_check(),
        *(probe[0] for probe in compiler_probes),
        _local_chain_probe(artifact),
    ]
    repository_checks = [
        _input_check(root),
        _script_json_check(
            root,
            name="locked-build-contract",
            script="code/scripts/verify_build_contract.py",
            remediation=(
                "Restore BUILD_MATRIX.json and the Python/uv/requirements lock files; "
                "use uv 0.11.29."
            ),
        ),
        _script_json_check(
            root,
            name="artifact-manifest",
            script="code/scripts/verify_artifact_manifest.py",
            remediation=(
                "Restore tracked artifacts or refresh ARTIFACT_MANIFEST.json only "
                "after an intentional public artifact change."
            ),
        ),
        _corpus_check(root),
    ]
    checks = (
        runtime_checks
        if runtime_only
        else [
            runtime_checks[0],
            *repository_checks,
            *runtime_checks[1:],
        ]
    )
    return {
        "schema_version": 1,
        "status": "pass" if all(item.status != "fail" for item in checks) else "fail",
        "project_root": str(root),
        "install_solc_requested": install_solc,
        "runtime_only": runtime_only,
        "network_may_be_required": install_solc,
        "checks": [asdict(item) for item in checks],
    }
