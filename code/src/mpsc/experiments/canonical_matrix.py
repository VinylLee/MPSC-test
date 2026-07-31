"""Canonical MyToken MR-by-mutant matrix with per-cell evidence."""

from __future__ import annotations

import csv
import importlib.metadata
import json
import platform
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..chain.local_backend import LocalChainBackend
from ..mutation.corpus import canonical_source_sha256
from ..serialization import sanitize_for_json
from ..solidity.compiler import compile_contract_solcx
from ..testing.canonical_executor import CanonicalExecutor
from ..testing.case_generation import generate_mytoken_mr6_cases

DEFAULT_SUBJECTS = {
    "original": Path("experiment-data/subjects/MyToken.sol"),
    "MUT-01": Path("experiment-data/mutants/MyToken/MUT-01/MyToken.sol"),
    "MUT-07": Path("experiment-data/mutants/MyToken/MUT-07/MyToken.sol"),
    "MUT-08": Path("experiment-data/mutants/MyToken/MUT-08/MyToken.sol"),
}
DEFAULT_MRS = ("MR6.1", "MR6.4", "MR6.6")


def run_canonical_mytoken_matrix(
    output_dir: str | Path,
    *,
    subjects: dict[str, Path] | None = None,
    mr_ids: tuple[str, ...] = DEFAULT_MRS,
    seed: int = 20260727,
    compiler_version: str = "0.4.11",
) -> dict[str, Any]:
    """Execute and persist a small, non-trivial semantic matrix."""

    output = Path(output_dir)
    cells_dir = output / "cells"
    cells_dir.mkdir(parents=True, exist_ok=True)
    selected_subjects = subjects or DEFAULT_SUBJECTS
    accounts = LocalChainBackend().get_accounts()
    generated = {
        case.template.mr_id: case
        for case in generate_mytoken_mr6_cases(accounts, seed=seed)
        if case.template.mr_id in mr_ids
    }
    missing_mrs = sorted(set(mr_ids) - set(generated))
    if missing_mrs:
        raise ValueError(f"unknown canonical MR IDs: {', '.join(missing_mrs)}")

    artifacts = {}
    subject_metadata = {}
    for subject_id, source_path in selected_subjects.items():
        path = Path(source_path)
        artifacts[subject_id] = compile_contract_solcx(path, compiler_version)
        subject_metadata[subject_id] = {
            "path": path.as_posix(),
            "sha256": canonical_source_sha256(path),
            "compile_success": artifacts[subject_id].success,
            "compile_errors": artifacts[subject_id].errors,
        }

    executor = CanonicalExecutor()
    cell_index: list[dict[str, Any]] = []
    matrix: dict[str, dict[str, int | None]] = {}
    baseline: dict[str, str | None] = {}
    for mr_id in mr_ids:
        case = generated[mr_id]
        matrix[mr_id] = {}
        for subject_id, artifact in artifacts.items():
            result = executor.execute(
                case.template,
                case.instance,
                case.pair,
                artifact,
            )
            verdict = result.verdict
            detection = (
                1 if verdict == "violation" else 0 if verdict == "pass" else None
            )
            if subject_id == "original":
                baseline[mr_id] = verdict
            else:
                matrix[mr_id][subject_id] = detection
            cell_id = f"{mr_id}__{subject_id}"
            predicate_components = (
                result.oracle_result.predicate_components
                if result.oracle_result is not None
                else []
            )
            required_predicates = [
                component for component in predicate_components if component.required
            ]
            cell = {
                "schema_version": 1,
                "cell_id": cell_id,
                "mr_id": mr_id,
                "subject_id": subject_id,
                "subject": subject_metadata[subject_id],
                "seed": seed,
                "pair": case.to_dict()["pair"],
                "execution_status": result.status,
                "binding": (
                    asdict(result.binding) if result.binding is not None else None
                ),
                "oracle_verdict": verdict,
                "detection": detection,
                "required_predicates_complete": (
                    bool(required_predicates)
                    and all(
                        component.status in {"satisfied", "violated"}
                        for component in required_predicates
                    )
                ),
                "source_observation": (
                    asdict(result.source_observation)
                    if result.source_observation is not None
                    else None
                ),
                "followup_observation": (
                    asdict(result.followup_observation)
                    if result.followup_observation is not None
                    else None
                ),
                "oracle_result": (
                    asdict(result.oracle_result)
                    if result.oracle_result is not None
                    else None
                ),
                "errors": result.errors,
            }
            cell_path = cells_dir / mr_id / f"{subject_id}.json"
            _write_json(cell_path, cell)
            cell_index.append(
                {
                    "cell_id": cell_id,
                    "mr_id": mr_id,
                    "subject_id": subject_id,
                    "status": result.status,
                    "verdict": verdict,
                    "detection": detection,
                    "evidence": cell_path.relative_to(output).as_posix(),
                }
            )

    mutant_ids = [
        subject_id for subject_id in selected_subjects if subject_id != "original"
    ]
    _write_detection_csv(output / "detection_matrix.csv", matrix, mutant_ids)
    _write_json(
        output / "detection_matrix.json",
        {
            "schema_version": 1,
            "mr_ids": list(mr_ids),
            "mutant_ids": mutant_ids,
            "matrix": matrix,
            "baseline": baseline,
        },
    )
    completed = sum(cell["status"] == "completed" for cell in cell_index)
    violations = sum(cell["verdict"] == "violation" for cell in cell_index)
    passes = sum(cell["verdict"] == "pass" for cell in cell_index)
    baseline_eligible = all(baseline.get(mr_id) == "pass" for mr_id in mr_ids)
    killed_mutants = sorted(
        mutant_id
        for mutant_id in mutant_ids
        if baseline_eligible
        and all(matrix[mr_id][mutant_id] is not None for mr_id in mr_ids)
        and any(matrix[mr_id][mutant_id] == 1 for mr_id in mr_ids)
    )
    indeterminate_mutants = sorted(
        mutant_id
        for mutant_id in mutant_ids
        if not baseline_eligible
        or any(matrix[mr_id][mutant_id] is None for mr_id in mr_ids)
    )
    surviving_mutants = sorted(
        mutant_id
        for mutant_id in mutant_ids
        if baseline_eligible and all(matrix[mr_id][mutant_id] == 0 for mr_id in mr_ids)
    )
    summary = {
        "schema_version": 1,
        "experiment": "canonical_mytoken_mr6_small",
        "git_commit": _git_commit(),
        "seed": seed,
        "compiler_version": compiler_version,
        "environment": _environment_metadata(),
        "mr_ids": list(mr_ids),
        "subjects": subject_metadata,
        "total_cells": len(cell_index),
        "completed_cells": completed,
        "pass_cells": passes,
        "violation_cells": violations,
        "baseline": baseline,
        "baseline_eligible": baseline_eligible,
        "killed_mutants": killed_mutants,
        "surviving_mutants": surviving_mutants,
        "indeterminate_mutants": indeterminate_mutants,
        "cells": cell_index,
    }
    _write_json(output / "summary.json", summary)
    _write_summary_markdown(output / "README.md", summary)
    return summary


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            sanitize_for_json(value),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_detection_csv(
    path: Path,
    matrix: dict[str, dict[str, int | None]],
    mutant_ids: list[str],
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["mr_id", *mutant_ids])
        for mr_id, row in matrix.items():
            writer.writerow(
                [
                    mr_id,
                    *[
                        row[mutant_id] if row[mutant_id] is not None else "E"
                        for mutant_id in mutant_ids
                    ],
                ]
            )


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except Exception:
        return "unknown"


def _environment_metadata() -> dict[str, str]:
    packages = {}
    for package in ("mpsc", "web3", "eth-tester", "py-evm", "py-solc-x"):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = "not-installed"
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        **packages,
    }


def _write_summary_markdown(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Canonical MyToken MR6 Small Matrix",
        "",
        f"- Git commit: `{summary['git_commit']}`",
        f"- Seed: `{summary['seed']}`",
        f"- Cells: {summary['completed_cells']}/{summary['total_cells']} completed",
        f"- Baseline eligible: {summary['baseline_eligible']}",
        f"- Verdicts: {summary['pass_cells']} pass, "
        f"{summary['violation_cells']} violation",
        f"- Killed mutants: {', '.join(summary['killed_mutants']) or 'none'}",
        f"- Surviving mutants: {', '.join(summary['surviving_mutants']) or 'none'}",
        f"- Indeterminate mutants: "
        f"{', '.join(summary['indeterminate_mutants']) or 'none'}",
        "",
        "This is a canonical engineering-mutant matrix from the MyToken control."
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
