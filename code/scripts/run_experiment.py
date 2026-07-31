from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_ROOT = (REPO_ROOT / "experiment-data" / "runs").resolve()

DECLARED_BLOCKERS: list[dict[str, str]] = []
SNAPSHOT_IGNORED_PARTS = {".git", ".venv", "__pycache__"}
SNAPSHOT_IGNORED_SUFFIXES = {".pyc", ".pyo"}


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _default_output(mode: str) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return RUNS_ROOT / f"{mode}-{stamp}"


def _resolve_output(raw: str | None, mode: str) -> Path:
    output = _default_output(mode) if raw is None else Path(raw)
    if not output.is_absolute():
        output = REPO_ROOT / output
    output = output.resolve()
    try:
        output.relative_to(RUNS_ROOT)
    except ValueError as error:
        raise ValueError(
            f"output must be inside {RUNS_ROOT}; refusing to write {output}"
        ) from error
    if output.exists() and any(output.iterdir()):
        raise ValueError(
            f"output directory is not empty: {output}; choose a new run directory"
        )
    output.mkdir(parents=True, exist_ok=True)
    return output


def _display_command(command: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(command)
    return shlex.join(command)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_published_path(repo_root: Path, raw_path: str) -> Path:
    posix = PurePosixPath(raw_path)
    if posix.is_absolute() or ".." in posix.parts or "\\" in raw_path:
        raise ValueError(f"unsafe manifest path: {raw_path!r}")
    resolved = (repo_root / Path(*posix.parts)).resolve()
    if resolved != repo_root and repo_root not in resolved.parents:
        raise ValueError(f"manifest path escapes repository: {raw_path!r}")
    return resolved


def _directory_snapshot(
    path: Path,
    *,
    runs_root: Path,
) -> dict[str, Any]:
    records: list[tuple[str, str]] = []
    for candidate in path.rglob("*"):
        relative = candidate.relative_to(path)
        if not candidate.is_file():
            continue
        if any(part in SNAPSHOT_IGNORED_PARTS for part in relative.parts):
            continue
        if candidate.suffix.lower() in SNAPSHOT_IGNORED_SUFFIXES:
            continue
        resolved = candidate.resolve()
        if resolved == runs_root or runs_root in resolved.parents:
            continue
        records.append((relative.as_posix(), _sha256(candidate)))
    records.sort()
    payload = "".join(f"{name}\0{digest}\n" for name, digest in records)
    return {
        "status": "captured",
        "file_count": len(records),
        "sha256_tree": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }


def capture_published_evidence_snapshot(
    repo_root: Path,
    *,
    manifest_path: Path | None = None,
    runs_root: Path | None = None,
) -> dict[str, Any]:
    """Snapshot every manifest-declared artifact without relying on Git."""

    root = repo_root.resolve()
    manifest = (
        (root / "ARTIFACT_MANIFEST.json")
        if manifest_path is None
        else manifest_path.resolve()
    )
    run_outputs = (
        (root / "experiment-data" / "runs").resolve()
        if runs_root is None
        else runs_root.resolve()
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    artifacts = payload.get("artifact_groups")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("ARTIFACT_MANIFEST.json has no artifact_groups")

    errors: list[str] = []
    records: dict[str, dict[str, Any]] = {}
    for index, artifact in enumerate(artifacts):
        artifact_id = artifact.get("id")
        raw_path = artifact.get("path")
        artifact_type = artifact.get("type")
        if not isinstance(artifact_id, str) or not artifact_id:
            errors.append(f"artifact_groups[{index}] has no stable id")
            continue
        if artifact_id in records:
            errors.append(f"duplicate artifact id: {artifact_id}")
            continue
        try:
            path = _safe_published_path(root, raw_path)
        except (TypeError, ValueError) as error:
            errors.append(f"{artifact_id}: {error}")
            continue
        if path == run_outputs or run_outputs in path.parents:
            errors.append(f"{artifact_id}: run output cannot be published evidence")
            continue
        record: dict[str, Any] = {
            "path": raw_path,
            "type": artifact_type,
        }
        if not path.exists():
            record["status"] = "missing"
            errors.append(f"{artifact_id}: missing {raw_path}")
        elif artifact_type == "file" and path.is_file():
            record.update(
                {
                    "status": "captured",
                    "sha256": _sha256(path),
                }
            )
        elif artifact_type == "directory" and path.is_dir():
            record.update(_directory_snapshot(path, runs_root=run_outputs))
        else:
            record["status"] = "type_mismatch"
            errors.append(f"{artifact_id}: expected {artifact_type} at {raw_path}")
        records[artifact_id] = record

    canonical = json.dumps(records, sort_keys=True, separators=(",", ":"))
    return {
        "schema_version": 1,
        "status": "pass" if not errors else "fail",
        "scope": (
            "ARTIFACT_MANIFEST.json and every manifest-declared artifact; "
            "experiment-data/runs and interpreter/cache files excluded"
        ),
        "manifest_sha256": _sha256(manifest),
        "artifact_count": len(records),
        "aggregate_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "artifacts": records,
        "errors": errors,
    }


def compare_published_evidence_snapshots(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    """Report all manifest, missing, changed, and newly declared state."""

    changes: list[dict[str, Any]] = []
    if before["manifest_sha256"] != after["manifest_sha256"]:
        changes.append(
            {
                "kind": "manifest_changed",
                "path": "ARTIFACT_MANIFEST.json",
            }
        )
    before_artifacts = before["artifacts"]
    after_artifacts = after["artifacts"]
    for artifact_id in sorted(set(before_artifacts) | set(after_artifacts)):
        old = before_artifacts.get(artifact_id)
        new = after_artifacts.get(artifact_id)
        if old is None:
            changes.append(
                {
                    "kind": "unexpected_manifest_artifact",
                    "artifact_id": artifact_id,
                    "path": new.get("path") if new else None,
                }
            )
        elif new is None:
            changes.append(
                {
                    "kind": "missing_manifest_artifact",
                    "artifact_id": artifact_id,
                    "path": old.get("path"),
                }
            )
        elif old != new:
            changes.append(
                {
                    "kind": (
                        "missing_or_invalid"
                        if new.get("status") != "captured"
                        else "content_changed"
                    ),
                    "artifact_id": artifact_id,
                    "path": new.get("path"),
                    "before_status": old.get("status"),
                    "after_status": new.get("status"),
                }
            )
    return {
        "status": "fail" if changes or after["status"] != "pass" else "pass",
        "modified": bool(changes),
        "changes": changes,
        "after_errors": after["errors"],
    }


def _steps(
    mode: str,
    output: Path,
    *,
    repo_root: Path = REPO_ROOT,
) -> list[dict[str, Any]]:
    python = sys.executable
    smoke = [
        {
            "id": "locked-build-contract",
            "evidence_class": "control",
            "command": [
                python,
                "code/scripts/verify_build_contract.py",
                "--check-export",
            ],
        },
        {
            "id": "doctor-json-read-only",
            "evidence_class": "control",
            "command": [
                python,
                "-m",
                "mpsc.cli",
                "doctor",
                "--json-output",
                "--project-root",
                str(repo_root),
            ],
        },
        {
            "id": "doctor-human-read-only",
            "evidence_class": "control",
            "command": [
                python,
                "-m",
                "mpsc.cli",
                "doctor",
                "--project-root",
                str(repo_root),
            ],
        },
        {
            "id": "artifact-manifest",
            "evidence_class": "control",
            "command": [python, "code/scripts/verify_artifact_manifest.py"],
        },
        {
            "id": "mutant-corpus-quick",
            "evidence_class": "control",
            "command": [
                python,
                "-m",
                "mpsc.cli",
                "verify-mutant-corpus",
            ],
        },
        {
            "id": "results-evidence-quick",
            "evidence_class": "control",
            "command": [
                python,
                "-m",
                "mpsc.cli",
                "verify-results-evidence",
            ],
        },
        {
            "id": "release-tests",
            "evidence_class": "control",
            "command": [
                python,
                "-m",
                "pytest",
                "-q",
                "code/tests/release",
            ],
        },
        {
            "id": "mytoken-reference-control",
            "evidence_class": "control",
            "command": [
                python,
                "-m",
                "mpsc.cli",
                "run-mytoken",
                "--output",
                str(output / "mytoken"),
            ],
        },
    ]
    if mode == "smoke":
        return smoke

    return [
        *smoke,
        {
            "id": "mutant-corpus-qualification",
            "evidence_class": "control",
            "command": [
                python,
                "-m",
                "mpsc.cli",
                "verify-mutant-corpus",
                "--qualify",
            ],
        },
        {
            "id": "subject-qualification",
            "evidence_class": "control",
            "command": [
                python,
                "-m",
                "mpsc.cli",
                "verify-results-evidence",
                "--qualify-subjects",
            ],
        },
        {
            "id": "llm-protocol-tests-no-provider",
            "evidence_class": "control",
            "command": [
                python,
                "-m",
                "pytest",
                "-q",
                "code/tests/unit/test_llm_offline.py",
                "code/tests/unit/test_vulnerability_review.py",
            ],
        },
        {
            "id": "full-test-suite",
            "evidence_class": "control",
            "command": [python, "-m", "pytest", "-q"],
        },
        {
            "id": "compute-tables",
            "evidence_class": "computed",
            "command": [
                python,
                "-m",
                "mpsc.cli",
                "render-tables",
                "--output",
                str(output / "tables"),
            ],
        },
        {
            "id": "compute-figures",
            "evidence_class": "computed",
            "command": [
                python,
                "-m",
                "mpsc.cli",
                "render-figures",
                "--output",
                str(output / "figures"),
            ],
        },
    ]


def _minimal_steps(
    mode: str,
    _output: Path,
    *,
    repo_root: Path = REPO_ROOT,
) -> list[dict[str, Any]]:
    python = sys.executable
    steps = [
        {
            "id": "locked-build-contract",
            "evidence_class": "control",
            "command": [
                python,
                "code/scripts/verify_build_contract.py",
            ],
        },
        {
            "id": "runtime-doctor",
            "evidence_class": "control",
            "command": [
                python,
                "-m",
                "mpsc.cli",
                "doctor",
                "--project-root",
                str(repo_root),
                "--runtime-only",
            ],
        },
    ]
    if mode == "available":
        steps.append(
            {
                "id": "core-unit-tests",
                "evidence_class": "control",
                "command": [
                    python,
                    "-m",
                    "pytest",
                    "-q",
                    "code/tests/unit/test_compiler.py",
                    "code/tests/unit/test_oracle.py",
                ],
            }
        )
    return steps


def run(
    mode: str,
    output: Path,
    *,
    repo_root: Path = REPO_ROOT,
    minimal: bool = False,
) -> int:
    started = _utc_now()
    root = repo_root.resolve()
    runs_root = (root / "experiment-data" / "runs").resolve()
    logs = output / "logs"
    logs.mkdir()
    command_log = output / "commands.jsonl"
    stages: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    before_snapshot: dict[str, Any] | None = None
    after_snapshot: dict[str, Any] | None = None
    comparison: dict[str, Any] | None = None
    before_error: str | None = None
    after_error: str | None = None

    print(f"[MPSC] mode={mode} output={output}", flush=True)
    if not minimal:
        try:
            before_snapshot = capture_published_evidence_snapshot(
                root,
                runs_root=runs_root,
            )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            before_error = f"{type(error).__name__}: {error}"
        if before_error or before_snapshot["status"] != "pass":
            failures.append(
                {
                    "stage": "published-evidence-precheck",
                    "exit_code": 1,
                    "remediation": (
                        "Restore ARTIFACT_MANIFEST.json and every declared artifact "
                        "before starting a run."
                    ),
                    "detail": (
                        before_error
                        if before_error
                        else "; ".join(before_snapshot["errors"])
                    ),
                }
            )

    if failures:
        steps = []
    elif minimal:
        steps = _minimal_steps(mode, output, repo_root=root)
    else:
        steps = _steps(mode, output, repo_root=root)
    for number, step in enumerate(steps, start=1):
        stage_start = time.monotonic()
        command = step["command"]
        display = _display_command(command)
        print(f"[MPSC] stage {number}: {step['id']}", flush=True)
        log_record = {
            "stage": step["id"],
            "evidence_class": step["evidence_class"],
            "command": command,
            "display_command": display,
            "started_at_utc": _utc_now(),
        }
        with command_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(log_record, ensure_ascii=False) + "\n")
        try:
            result = subprocess.run(
                command,
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as error:
            result = subprocess.CompletedProcess(
                command,
                1,
                "",
                f"{type(error).__name__}: {error}",
            )
        (logs / f"{number:02d}-{step['id']}.stdout.log").write_text(
            result.stdout,
            encoding="utf-8",
        )
        (logs / f"{number:02d}-{step['id']}.stderr.log").write_text(
            result.stderr,
            encoding="utf-8",
        )
        stage = {
            "id": step["id"],
            "evidence_class": step["evidence_class"],
            "status": "pass" if result.returncode == 0 else "fail",
            "exit_code": result.returncode,
            "duration_seconds": round(time.monotonic() - stage_start, 3),
            "stdout_log": (logs / f"{number:02d}-{step['id']}.stdout.log")
            .relative_to(output)
            .as_posix(),
            "stderr_log": (logs / f"{number:02d}-{step['id']}.stderr.log")
            .relative_to(output)
            .as_posix(),
        }
        stages.append(stage)
        if result.returncode != 0:
            failures.append(
                {
                    "stage": step["id"],
                    "exit_code": result.returncode,
                    "remediation": (
                        f"Inspect {stage['stdout_log']} and "
                        f"{stage['stderr_log']}; run scripts/bootstrap for "
                        "dependency/compiler failures, or restore the tracked "
                        "evidence for integrity failures."
                    ),
                }
            )
            print(
                f"[MPSC] FAIL stage={step['id']} exit={result.returncode}",
                file=sys.stderr,
                flush=True,
            )
            break

    if (
        not minimal
        and before_snapshot is not None
        and before_snapshot["status"] == "pass"
    ):
        try:
            after_snapshot = capture_published_evidence_snapshot(
                root,
                runs_root=runs_root,
            )
            comparison = compare_published_evidence_snapshots(
                before_snapshot,
                after_snapshot,
            )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            after_error = f"{type(error).__name__}: {error}"
        if after_error or comparison["status"] != "pass":
            failures.append(
                {
                    "stage": "published-evidence-postcheck",
                    "exit_code": 1,
                    "remediation": (
                        "Inspect the evidence snapshot changes, restore the "
                        "published artifact, and rerun in a new runs directory."
                    ),
                    "detail": (
                        after_error
                        if after_error
                        else comparison["changes"] or comparison["after_errors"]
                    ),
                }
            )

    published_evidence_modified: bool | None
    if minimal:
        published_evidence_modified = False
    elif before_snapshot is None or before_snapshot["status"] != "pass":
        published_evidence_modified = None
    elif after_error:
        published_evidence_modified = True
    else:
        published_evidence_modified = bool(comparison["modified"])
    evidence_check = {
        "status": (
            "skipped"
            if minimal
            else (
                "not_established"
                if published_evidence_modified is None
                else ("fail" if published_evidence_modified else "pass")
            )
        ),
        "scope": (
            before_snapshot["scope"]
            if before_snapshot is not None
            else (
                "ARTIFACT_MANIFEST.json and every manifest-declared artifact; "
                "experiment-data/runs and interpreter/cache files excluded"
            )
        ),
        "before_aggregate_sha256": (
            before_snapshot.get("aggregate_sha256")
            if before_snapshot is not None
            else None
        ),
        "after_aggregate_sha256": (
            after_snapshot.get("aggregate_sha256")
            if after_snapshot is not None
            else None
        ),
        "before_error": before_error,
        "after_error": after_error,
        "changes": comparison["changes"] if comparison is not None else [],
    }
    summary = {
        "schema_version": 1,
        "mode": mode,
        "evidence_class": "control",
        "minimal_run": minimal,
        "status": "fail" if failures else "pass",
        "started_at_utc": started,
        "finished_at_utc": _utc_now(),
        "project_root": str(root),
        "run_directory": str(output),
        "network_used_by_runner": False,
        "provider_calls_made": 0,
        "published_evidence_modified": published_evidence_modified,
        "published_evidence_check": evidence_check,
        "stages": stages,
        "failure": failures[0] if failures else None,
        "failures": failures,
    }
    summary_path = output / "run_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"[MPSC] status={summary['status']} summary={summary_path}",
        flush=True,
    )
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("smoke", "available"))
    parser.add_argument(
        "--output",
        help="Run directory under experiment-data/runs/ (default: UTC-stamped).",
    )
    parser.add_argument(
        "--minimal",
        action="store_true",
        help="Run the portable core checks without repository state gates.",
    )
    args = parser.parse_args()
    try:
        output = _resolve_output(args.output, args.mode)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return run(args.mode, output, minimal=args.minimal)


if __name__ == "__main__":
    raise SystemExit(main())
