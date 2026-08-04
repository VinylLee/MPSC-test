"""Validation and analysis helpers for the ItyFuzz comparison campaign."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG = Path("code/configs/comparison_tools/ityfuzz_campaign.yaml")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_count(path: Path) -> int:
    return sum(1 for item in path.rglob("*") if item.is_file())


def validate_campaign(
    config_path: str | Path = DEFAULT_CONFIG,
    *,
    project_root: str | Path = ".",
) -> dict[str, Any]:
    """Validate campaign inputs, recorded runs, and the pinned tool revision."""

    root = Path(project_root).resolve()
    config_file = root / Path(config_path)
    errors: list[str] = []
    if not config_file.is_file():
        return {"status": "fail", "errors": [f"missing config: {config_file}"]}

    payload = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if payload.get("campaign_id") != "mpsc-ityfuzz-comparison-v1":
        errors.append("unexpected campaign_id")

    subjects = payload.get("subjects", [])
    for subject in subjects:
        relative = Path(subject["path"])
        path = root / relative
        if path.is_absolute() and root not in path.parents:
            errors.append(f"subject escapes project root: {relative.as_posix()}")
            continue
        if not path.is_file():
            errors.append(f"missing subject: {relative.as_posix()}")
        elif _sha256(path) != subject["sha256"]:
            errors.append(f"subject hash mismatch: {relative.as_posix()}")

    runs = payload.get("recorded_runs", [])
    observed_run_files = 0
    for run in runs:
        relative = Path(run["path"])
        path = root / relative
        if not path.is_dir():
            errors.append(f"missing recorded run: {relative.as_posix()}")
            continue
        count = _file_count(path)
        observed_run_files += count
        if count != run["file_count"]:
            errors.append(
                f"recorded run file count mismatch: {relative.as_posix()} "
                f"({count} != {run['file_count']})"
            )

    tool = payload.get("tool", {})
    tool_path = root / Path(tool.get("source_path", ""))
    observed_commit = None
    if not tool_path.is_dir():
        errors.append(f"missing ItyFuzz source: {tool_path}")
    else:
        marker = tool_path / ".mpsc-pinned-commit"
        if not marker.is_file():
            errors.append("missing pinned revision marker (.mpsc-pinned-commit)")
        else:
            observed_commit = marker.read_text(encoding="utf-8").strip()
            if observed_commit != tool.get("commit"):
                errors.append(
                    f"ItyFuzz revision mismatch: {observed_commit} != "
                    f"{tool.get('commit')}"
                )

    required_paths = payload.get("supporting_artifacts", [])
    for relative_text in required_paths:
        relative = Path(relative_text)
        if not (root / relative).exists():
            errors.append(f"missing supporting artifact: {relative.as_posix()}")

    return {
        "status": "pass" if not errors else "fail",
        "campaign_id": payload.get("campaign_id"),
        "subject_count": len(subjects),
        "recorded_run_count": len(runs),
        "recorded_run_file_count": observed_run_files,
        "ityfuzz_commit": observed_commit,
        "errors": errors,
    }


def _start_time_from_log(log_path: Path) -> float | None:
    if not log_path.is_file():
        return None
    pattern = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = pattern.search(line)
        if match:
            return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
    return None


def analyze_detection_time(
    run_dir: str | Path,
    *,
    function_name: str = "batchTransfer",
    value_markers: tuple[str, ...] = (
        "578960",
        "117736",
        "340282366920938463463",
    ),
) -> dict[str, Any]:
    """Find the first corpus item matching a function and characteristic values."""

    run = Path(run_dir)
    corpus = run / "corpus"
    if not corpus.is_dir():
        return {"status": "fail", "errors": [f"missing corpus: {corpus}"]}

    candidates = sorted(
        (path for path in corpus.iterdir() if path.is_file()),
        key=lambda path: path.stat().st_mtime,
    )
    start_time = _start_time_from_log(run / "fuzz.log")
    if start_time is None and candidates:
        start_time = candidates[0].stat().st_mtime

    first_match = None
    for candidate in candidates:
        text = candidate.read_text(encoding="utf-8", errors="replace")
        if function_name in text and any(marker in text for marker in value_markers):
            first_match = candidate
            break

    if first_match is None:
        return {
            "status": "not_found",
            "function_name": function_name,
            "corpus_file_count": len(candidates),
            "errors": [],
        }

    detected_at = first_match.stat().st_mtime
    return {
        "status": "pass",
        "function_name": function_name,
        "first_matching_input": first_match.as_posix(),
        "elapsed_seconds": max(0.0, detected_at - start_time) if start_time else None,
        "corpus_file_count": len(candidates),
        "errors": [],
    }
