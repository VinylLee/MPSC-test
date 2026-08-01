"""Repeated canonical MyToken cells for mutation evidence."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from ..chain.local_backend import LocalChainBackend
from ..mutation.corpus import (
    DEFAULT_CORPUS,
    canonical_source_sha256,
    validate_frozen_corpus,
)
from ..serialization import sanitize_for_json
from ..solidity.compiler import compile_contract_solcx
from ..testing.canonical_executor import CanonicalExecutionResult, CanonicalExecutor
from ..testing.case_generation import generate_mytoken_mr6_cases
from .canonical_matrix import DEFAULT_MRS, _environment_metadata, _git_commit


def run_repeated_mytoken_matrix(
    output_dir: str | Path,
    *,
    repetitions: int = 10,
    seed: int = 20260727,
    compiler_version: str = "0.4.11",
    corpus_config: str | Path = DEFAULT_CORPUS,
) -> dict[str, Any]:
    """Run every canonical MR-subject cell on a fresh chain repeatedly."""

    if repetitions < 1:
        raise ValueError("repetitions must be at least 1")
    corpus = validate_frozen_corpus(corpus_config)
    if not corpus["valid"]:
        raise ValueError("frozen mutant corpus failed validation")

    output = Path(output_dir)
    config = yaml.safe_load(Path(corpus_config).read_text(encoding="utf-8"))
    subjects = {"original": Path(config["subject"]["path"])}
    subjects.update(
        {
            item["mutant_id"]: Path(item["path"])
            for item in config["mutants"]
            if item["eligibility_status"] == "eligible"
        }
    )

    accounts = LocalChainBackend().get_accounts()
    cases = {
        generated.template.mr_id: generated
        for generated in generate_mytoken_mr6_cases(accounts, seed=seed)
        if generated.template.mr_id in DEFAULT_MRS
    }
    artifacts = {
        subject_id: compile_contract_solcx(path, compiler_version)
        for subject_id, path in subjects.items()
    }
    unsuccessful = [
        subject_id
        for subject_id, artifact in artifacts.items()
        if not artifact.success or not artifact.bytecode
    ]
    if unsuccessful:
        raise RuntimeError("canonical compilation failed: " + ", ".join(unsuccessful))

    executor = CanonicalExecutor()
    run_index: list[dict[str, Any]] = []
    results: dict[tuple[str, str, int], dict[str, Any]] = {}
    for mr_id in DEFAULT_MRS:
        case = cases[mr_id]
        for repetition in range(1, repetitions + 1):
            for subject_id, artifact in artifacts.items():
                result = executor.execute(
                    case.template,
                    case.instance,
                    case.pair,
                    artifact,
                )
                record = _run_record(
                    result=result,
                    mr_id=mr_id,
                    subject_id=subject_id,
                    repetition=repetition,
                    seed=seed,
                    state_strategy=case.pair.state_strategy,
                    source_path=subjects[subject_id],
                )
                relative_path = (
                    Path("runs") / mr_id / subject_id / f"run-{repetition:02d}.json"
                )
                _write_json(output / relative_path, record)
                record["evidence"] = relative_path.as_posix()
                results[(mr_id, subject_id, repetition)] = record
                run_index.append(_index_record(record))

    cells = _aggregate_cells(results, repetitions)
    summary = {
        "schema_version": 1,
        "experiment": "canonical_mytoken_optimization_repetitions",
        "claim_scope": "control_only",
        "git_commit": _git_commit(),
        "seed": seed,
        "compiler_version": compiler_version,
        "environment": _environment_metadata(),
        "corpus_id": corpus["corpus_id"],
        "repetitions_per_cell": repetitions,
        "mr_ids": list(DEFAULT_MRS),
        "subject_ids": list(subjects),
        "mutant_ids": [
            subject_id for subject_id in subjects if subject_id != "original"
        ],
        "total_runs": len(run_index),
        "completed_runs": sum(
            run["execution_status"] == "completed" for run in run_index
        ),
        "error_runs": sum(run["execution_status"] != "completed" for run in run_index),
        "complete_required_predicate_runs": sum(
            run["required_predicates_complete"] for run in run_index
        ),
        "cells": cells,
        "runs": run_index,
    }
    _write_json(output / "summary.json", summary)
    _write_json(
        output / "cells.json",
        {
            "schema_version": 1,
            "repetitions_per_cell": repetitions,
            "cells": cells,
        },
    )
    _write_readme(output / "README.md", summary)
    return summary


def _run_record(
    *,
    result: CanonicalExecutionResult,
    mr_id: str,
    subject_id: str,
    repetition: int,
    seed: int,
    state_strategy: str,
    source_path: Path,
) -> dict[str, Any]:
    oracle = result.oracle_result
    predicates = oracle.predicate_components if oracle is not None else []
    required = [predicate for predicate in predicates if predicate.required]
    required_complete = bool(required) and all(
        predicate.status in {"satisfied", "violated"} for predicate in required
    )
    return {
        "schema_version": 1,
        "run_id": f"{mr_id}__{subject_id}__{repetition:02d}",
        "mr_id": mr_id,
        "subject_id": subject_id,
        "repetition": repetition,
        "seed": seed,
        "source_path": source_path.as_posix(),
        "source_sha256": canonical_source_sha256(source_path),
        "state_strategy": state_strategy,
        "fresh_state_required": state_strategy == "fresh_deployment",
        "execution_status": result.status,
        "oracle_verdict": result.verdict,
        "required_predicate_count": len(required),
        "required_predicates_complete": required_complete,
        "errors": list(result.errors),
        "binding": asdict(result.binding) if result.binding is not None else None,
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
        "oracle_result": asdict(oracle) if oracle is not None else None,
    }


def _index_record(record: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "run_id",
        "mr_id",
        "subject_id",
        "repetition",
        "execution_status",
        "oracle_verdict",
        "required_predicate_count",
        "required_predicates_complete",
        "errors",
        "evidence",
    )
    return {key: record[key] for key in keys}


def _aggregate_cells(
    results: dict[tuple[str, str, int], dict[str, Any]],
    repetitions: int,
) -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    mutant_ids = sorted(
        {subject_id for _, subject_id, _ in results if subject_id != "original"}
    )
    mr_ids = list(dict.fromkeys(mr_id for mr_id, _, _ in results))
    for mr_id in mr_ids:
        for mutant_id in mutant_ids:
            baseline_runs = [
                results[(mr_id, "original", repetition)]
                for repetition in range(1, repetitions + 1)
            ]
            mutant_runs = [
                results[(mr_id, mutant_id, repetition)]
                for repetition in range(1, repetitions + 1)
            ]
            eligible_pairs = [
                (baseline, mutant)
                for baseline, mutant in zip(baseline_runs, mutant_runs, strict=True)
                if baseline["execution_status"] == "completed"
                and baseline["oracle_verdict"] == "pass"
                and baseline["required_predicates_complete"]
                and mutant["execution_status"] == "completed"
                and mutant["required_predicates_complete"]
                and mutant["oracle_verdict"] in {"pass", "violation"}
            ]
            verdicts = [mutant["oracle_verdict"] for _, mutant in eligible_pairs]
            errors = [
                error
                for run in [*baseline_runs, *mutant_runs]
                for error in run["errors"]
            ]
            cells.append(
                {
                    "cell_id": f"{mr_id}__{mutant_id}",
                    "mr_id": mr_id,
                    "mutant_id": mutant_id,
                    "planned_executions": repetitions,
                    "TCE": len(eligible_pairs),
                    "TCK": verdicts.count("violation"),
                    "error_count": len(errors),
                    "errors": errors,
                    "verdict_counts": {
                        verdict: verdicts.count(verdict)
                        for verdict in ("pass", "violation")
                    },
                    "stable": len(set(verdicts)) == 1 and len(verdicts) == repetitions,
                    "baseline_pass_count": sum(
                        run["oracle_verdict"] == "pass"
                        and run["required_predicates_complete"]
                        and run["execution_status"] == "completed"
                        for run in baseline_runs
                    ),
                }
            )
    return cells


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            sanitize_for_json(value),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_readme(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Canonical MyToken repeated mutation cells",
        "",
        f"- Runs: {summary['completed_runs']}/{summary['total_runs']} completed",
        f"- Repetitions per MR/subject cell: {summary['repetitions_per_cell']}",
        "- State strategy: fresh deployment for every source/follow-up pair",
        f"- Claim scope: `{summary['claim_scope']}`",
        "",
        "| MR | Mutant | TCK | TCE | Stable | Errors |",
        "| --- | --- | ---: | ---: | --- | ---: |",
    ]
    for cell in summary["cells"]:
        lines.append(
            f"| {cell['mr_id']} | {cell['mutant_id']} | "
            f"{cell['TCK']} | {cell['TCE']} | "
            f"{str(cell['stable']).lower()} | {cell['error_count']} |"
        )
    lines.extend(
        [
            "",
            "These are engineering-control executions."
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
