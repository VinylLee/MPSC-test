"""Derive Eq.2 kill vectors and Eq.3 scores from canonical raw runs."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from ..mutation.mutation_score import (
    compute_kill_vector,
    compute_mutation_score,
)

DEFAULT_REPETITIONS = Path(
    "experiment-data/results/canonical/mytoken_optimization/repetitions"
)


def derive_canonical_mutation_scores(
    output_dir: str | Path,
    *,
    repetitions_dir: str | Path = DEFAULT_REPETITIONS,
    tau: float = 0.1,
) -> dict[str, Any]:
    """Recompute complete paired cells from raw run evidence."""

    source = Path(repetitions_dir)
    repeated_summary = _read_json(source / "summary.json")
    mr_ids = repeated_summary["mr_ids"]
    mutant_ids = repeated_summary["mutant_ids"]
    repetitions = int(repeated_summary["repetitions_per_cell"])
    expected_runs = repetitions * len(mr_ids) * (len(mutant_ids) + 1)

    records: dict[tuple[str, str, int], dict[str, Any]] = {}
    for path in sorted((source / "runs").glob("*/*/run-*.json")):
        record = _read_json(path)
        key = (
            record["mr_id"],
            record["subject_id"],
            int(record["repetition"]),
        )
        if key in records:
            raise ValueError(f"duplicate raw run: {key}")
        records[key] = record
    if len(records) != expected_runs:
        raise ValueError(
            f"incomplete raw run set: expected {expected_runs}, found {len(records)}"
        )

    cells: list[dict[str, Any]] = []
    vectors: dict[str, dict[str, int]] = {}
    scores: dict[str, float] = {}
    for mr_id in mr_ids:
        tck: dict[str, int] = {}
        tce: dict[str, int] = {}
        for mutant_id in mutant_ids:
            paired = []
            for repetition in range(1, repetitions + 1):
                baseline = records[(mr_id, "original", repetition)]
                mutant = records[(mr_id, mutant_id, repetition)]
                if not _baseline_eligible(baseline):
                    raise ValueError(
                        f"ineligible baseline: {mr_id} repetition {repetition}"
                    )
                if not _mutant_eligible(mutant):
                    raise ValueError(
                        f"ineligible mutant run: {mr_id}/{mutant_id} "
                        f"repetition {repetition}"
                    )
                paired.append(mutant)
            tce[mutant_id] = len(paired)
            tck[mutant_id] = sum(run["oracle_verdict"] == "violation" for run in paired)
            ratio = tck[mutant_id] / tce[mutant_id]
            cells.append(
                {
                    "mr_id": mr_id,
                    "mutant_id": mutant_id,
                    "TCK": tck[mutant_id],
                    "TCE": tce[mutant_id],
                    "detection_ratio": ratio,
                    "tau": tau,
                    "K_ik": int(ratio >= tau),
                }
            )
        vector = compute_kill_vector(
            mr_id,
            mutant_ids,
            detection_counts=tck,
            total_executions=tce,
            tau=tau,
        )
        vectors[mr_id] = {
            mutant_id: int(vector.kills[mutant_id]) for mutant_id in mutant_ids
        }
        scores[mr_id] = compute_mutation_score(vector)

    result = {
        "schema_version": 1,
        "experiment": "canonical_mytoken_eq2_eq3",
        "claim_scope": "control_only",
        "source_repetitions": source.as_posix(),
        "raw_runs_consumed": len(records),
        "tau": tau,
        "mr_ids": mr_ids,
        "mutant_ids": mutant_ids,
        "cells": cells,
        "kill_vectors": vectors,
        "mutation_scores": scores,
    }
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    _write_json(output / "kill_vectors.json", result)
    _write_scores_csv(output / "mutation_scores.csv", mr_ids, scores)
    _write_readme(output / "README.md", result)
    return result


def _baseline_eligible(run: dict[str, Any]) -> bool:
    return (
        run["execution_status"] == "completed"
        and run["oracle_verdict"] == "pass"
        and run["required_predicates_complete"] is True
        and not run["errors"]
    )


def _mutant_eligible(run: dict[str, Any]) -> bool:
    return (
        run["execution_status"] == "completed"
        and run["oracle_verdict"] in {"pass", "violation"}
        and run["required_predicates_complete"] is True
        and not run["errors"]
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_scores_csv(
    path: Path,
    mr_ids: list[str],
    scores: dict[str, float],
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["mr_id", "mutation_score"])
        for mr_id in mr_ids:
            writer.writerow([mr_id, f"{scores[mr_id]:.12g}"])


def _write_readme(path: Path, result: dict[str, Any]) -> None:
    lines = [
        "# Canonical MyToken Eq.2 and Eq.3 results",
        "",
        f"- Raw runs consumed: {result['raw_runs_consumed']}",
        f"- Detection threshold tau: {result['tau']}",
        f"- Claim scope: `{result['claim_scope']}`",
        "",
        "| MR | Kill vector | Mutation score |",
        "| --- | --- | ---: |",
    ]
    for mr_id in result["mr_ids"]:
        vector = [
            result["kill_vectors"][mr_id][mutant_id]
            for mutant_id in result["mutant_ids"]
        ]
        lines.append(f"| {mr_id} | {vector} | {result['mutation_scores'][mr_id]:.6f} |")
    lines.extend(
        [
            "",
            "Scores are derived from complete raw engineering-control cells."
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
