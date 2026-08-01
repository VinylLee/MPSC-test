"""Read-only validation for subject qualification and published result lineage."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from .config import MPSCConfig
from .contracts.profile import (
    compile_profile_abi,
    load_contract_profile,
    validate_profile_abi,
)
from .contracts.profile_runtime import deploy_profile
from .models import InputRelation, KillVector, MetamorphicRelation, OutputRelation
from .mr.distance import compute_difference_score, compute_jaccard_distance
from .mr.optimizer import optimize_mr_category_with_trace

EVIDENCE_CLASSES = {
    "computed",
    "control",
    "verified",
}
TEXT_SUFFIXES = {
    ".csv",
    ".json",
    ".md",
    ".py",
    ".sol",
    ".toml",
    ".yaml",
    ".yml",
}
EXPECTED_SUBJECT_IDS = {
    "mytoken",
    "rubixi",
    "bectoken",
    "gnosissafeproxy",
    "personal_bank",
}
EXPECTED_MR_IDS = ["MR6.1", "MR6.4", "MR6.6"]
EXPECTED_MUTANT_IDS = ["MUT-01", "MUT-07", "MUT-08"]
EXPECTED_INDEX_ID = "mpsc-results-evidence-chain-v1"
EXPECTED_SUBJECT_MANIFEST_ID = "mpsc-five-subject-qualification-v1"
EXPECTED_ARTIFACT_LINEAGE = {
    "five_subject_qualification": ("control", ()),
    "mytoken_canonical_matrix": (
        "control",
        ("five_subject_qualification",),
    ),
    "mytoken_repetitions": (
        "control",
        ("mytoken_canonical_matrix",),
    ),
    "mytoken_scores": ("control", ("mytoken_repetitions",)),
    "mytoken_optimizer": ("control", ("mytoken_scores",)),
    "aggregate_results": ("computed", ()),
    "computed_tables": (
        "computed",
        ("aggregate_results",),
    ),
    "computed_figures": (
        "computed",
        ("aggregate_results", "computed_tables"),
    ),
    "comparison_aggregates": (
        "computed",
        ("aggregate_results",),
    ),
    "timing_aggregates": (
        "computed",
        ("aggregate_results",),
    ),
}
EXPECTED_PROCESSED_MAPPINGS = {
    "table-3": (
        "experiment-data/processed/mutant_counts.csv",
        "experiment-data/processed/computed/mutants.csv",
    ),
    "table-4": (
        "experiment-data/processed/mutation_scores.csv",
        "experiment-data/processed/computed/mutation_scores.csv",
    ),
    "table-5": (
        "experiment-data/processed/llm_identification.csv",
        "experiment-data/processed/computed/llm_effectiveness.csv",
    ),
    "table-6": (
        "experiment-data/processed/llm_efficiency.csv",
        "experiment-data/processed/computed/llm_efficiency.csv",
    ),
    "table-7": (
        "experiment-data/processed/vulnerability_findings.csv",
        "experiment-data/processed/computed/target_vulnerabilities.csv",
    ),
    "table-8": (
        "experiment-data/processed/vulnerability_findings.csv",
        "experiment-data/processed/computed/vulnerability_totals.csv",
    ),
    "table-9": (
        "experiment-data/processed/optimization_metrics.csv",
        "experiment-data/processed/computed/optimization.csv",
    ),
    "figure-7": (
        "experiment-data/processed/subject_mr_counts.csv",
        "experiment-data/results/reports/figures/mr_counts.png",
    ),
    "figure-8": (
        "experiment-data/processed/mr_method_comparison.csv",
        "experiment-data/results/reports/figures/method_comparison.png",
    ),
    "figure-9": (
        "experiment-data/processed/computed/vulnerability_totals.csv",
        "experiment-data/results/reports/figures/vulnerability_comparison.png",
    ),
    "figure-10": (
        "experiment-data/processed/computed/optimization.csv",
        "experiment-data/results/reports/figures/optimization.png",
    ),
    "figure-11": (
        "experiment-data/processed/method_time_comparison.csv",
        "experiment-data/results/reports/figures/method_time.png",
    ),
    "appendix-mr-sensitivity": (
        "experiment-data/processed/mytoken_mr_sensitivity.csv",
        "experiment-data/results/reports/figures/appendix_mr_sensitivity.png",
    ),
    "appendix-mrd": (
        "experiment-data/processed/mytoken_mrd_pairs.csv",
        "experiment-data/results/reports/figures/appendix_mrd_distribution.png",
    ),
}
EXPECTED_SUBJECT_MAPPING = {
    "mytoken": (
        "experiment-data/subjects/MyToken.sol",
        "code/configs/contracts/mytoken.yaml",
        "0.4.11",
        "MyToken",
    ),
    "rubixi": (
        "experiment-data/subjects/Rubixi/Rubixi.sol",
        "code/configs/contracts/rubixi.yaml",
        "0.4.16",
        "Rubixi",
    ),
    "bectoken": (
        "experiment-data/subjects/BecToken/BecToken.sol",
        "code/configs/contracts/bectoken.yaml",
        "0.4.16",
        "BecToken",
    ),
    "gnosissafeproxy": (
        "experiment-data/subjects/GnosisSafeProxy/GnosisSafeProxy.sol",
        "code/configs/contracts/gnosissafeproxy.yaml",
        "0.7.6",
        "GnosisSafeProxy",
    ),
    "personal_bank": (
        "experiment-data/subjects/PERSONAL_BANK/PERSONAL_BANK.sol",
        "code/configs/contracts/personal_bank.yaml",
        "0.4.19",
        "PERSONAL_BANK",
    ),
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _repository_path(root: Path, raw_path: str) -> Path:
    posix = PurePosixPath(raw_path)
    if posix.is_absolute() or ".." in posix.parts or "\\" in raw_path:
        raise ValueError(f"unsafe repository-relative path: {raw_path!r}")
    resolved = (root / Path(*posix.parts)).resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"path escapes repository root: {raw_path!r}")
    return resolved


def _safe_child_path(root: Path, raw_path: str) -> Path:
    posix = PurePosixPath(raw_path)
    if posix.is_absolute() or ".." in posix.parts or "\\" in raw_path:
        raise ValueError(f"unsafe child path: {raw_path!r}")
    resolved = (root / Path(*posix.parts)).resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"child path escapes its evidence root: {raw_path!r}")
    return resolved


def _file_digest(path: Path) -> str:
    content = path.read_bytes()
    if path.suffix.lower() in TEXT_SUFFIXES:
        content = content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(content).hexdigest()


def _tree_digest(path: Path) -> tuple[str, int]:
    records: list[str] = []
    for candidate in path.rglob("*"):
        if not candidate.is_file() or "__pycache__" in candidate.parts:
            continue
        if candidate.suffix.lower() in {".pyc", ".pyo"}:
            continue
        relative = candidate.relative_to(path).as_posix()
        strategy = (
            "sha256_lf_normalized_text"
            if candidate.suffix.lower() in TEXT_SUFFIXES
            else "sha256_bytes"
        )
        records.append(f"{relative}\0{strategy}\0{_file_digest(candidate)}\n")
    records.sort()
    digest = hashlib.sha256("".join(records).encode("utf-8")).hexdigest()
    return digest, len(records)


def _resolve_argument(value: Any, deployed: Any) -> Any:
    if isinstance(value, dict) and "role" in value:
        return deployed.roles[value["role"]]
    return value


def _check_expectation(
    value: Any,
    expectation: dict[str, Any],
    deployed: Any,
) -> bool:
    if len(expectation) != 1:
        raise ValueError("qualification expectation must have exactly one operator")
    if "equals" in expectation:
        return value == expectation["equals"]
    if "equals_role" in expectation:
        return str(value).lower() == deployed.roles[expectation["equals_role"]].lower()
    if "sequence_first_equals" in expectation:
        return bool(value) and value[0] == expectation["sequence_first_equals"]
    if "greater_than" in expectation:
        return value > expectation["greater_than"]
    raise ValueError(f"unsupported qualification expectation: {expectation!r}")


def _qualify_subject(entry: dict[str, Any], root: Path) -> list[str]:
    errors: list[str] = []
    profile_path = _repository_path(root, entry["profile_path"])
    deployed = deploy_profile(profile_path)
    for step in entry["qualification"]["steps"]:
        arguments = [
            _resolve_argument(value, deployed) for value in step.get("arguments", [])
        ]
        try:
            if step["action"] == "observe":
                value = deployed.observe(
                    step["observer"],
                    arguments,
                    step.get("caller_role", "owner"),
                )
                if not _check_expectation(value, step["expect"], deployed):
                    errors.append(
                        f"{entry['subject_id']}:{step['id']} unexpected observation "
                        f"{value!r}"
                    )
            elif step["action"] == "transact":
                receipt = deployed.transact(
                    step["function"],
                    arguments,
                    step.get("caller_role", "owner"),
                    int(step.get("value", 0)),
                )
                if receipt.success is not step["expect_success"]:
                    errors.append(
                        f"{entry['subject_id']}:{step['id']} transaction success "
                        f"was {receipt.success!r}"
                    )
            else:
                errors.append(
                    f"{entry['subject_id']}:{step['id']} unsupported action "
                    f"{step['action']!r}"
                )
        except Exception as error:  # qualification reports all runtime failures
            errors.append(f"{entry['subject_id']}:{step['id']} failed: {error}")
    return errors


def validate_subject_manifest(
    manifest_path: str | Path,
    *,
    base_dir: str | Path = ".",
    qualify: bool = False,
) -> dict[str, Any]:
    """Validate the subject identity layer, optionally on fresh chains."""

    root = Path(base_dir).resolve()
    errors: list[str] = []
    try:
        manifest = _read_json(Path(manifest_path))
    except (OSError, json.JSONDecodeError) as error:
        return {"status": "fail", "errors": [f"cannot read subject manifest: {error}"]}

    if manifest.get("schema_version") != 1:
        errors.append("subject manifest schema_version must equal 1")
    if manifest.get("manifest_id") != EXPECTED_SUBJECT_MANIFEST_ID:
        errors.append("subject manifest_id changed")
    if manifest.get("evidence_class") != "control":
        errors.append("subject manifest must be control")
    if not manifest.get("hash_policy"):
        errors.append("subject manifest hash_policy is required")
    entries = manifest.get("subjects", [])
    if not isinstance(entries, list):
        errors.append("subjects must be a list")
        entries = []
    ids = [
        entry.get("subject_id") if isinstance(entry, dict) else None
        for entry in entries
    ]
    if len(entries) != 5 or set(ids) != EXPECTED_SUBJECT_IDS:
        errors.append("subject manifest must contain exactly the five stable subjects")
    if len(ids) != len(set(ids)):
        errors.append("subject IDs must be unique")

    source_paths: set[str] = set()
    profile_paths: set[str] = set()
    qualified = 0
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("each subject entry must be an object")
            continue
        subject_id = entry.get("subject_id", "<missing>")
        prefix = f"subject {subject_id}"
        if entry.get("evidence_class") != "control":
            errors.append(f"{prefix}: evidence_class must be control")
        if entry.get("mr_binding_status") != "verified":
            errors.append(f"{prefix}: mr_binding_status must be verified")
        if not entry.get("qualification", {}).get("steps"):
            errors.append(f"{prefix}: qualification steps are required")
        expected_mapping = EXPECTED_SUBJECT_MAPPING.get(subject_id)
        observed_mapping = (
            entry.get("source_path"),
            entry.get("profile_path"),
            entry.get("compiler"),
            entry.get("contract_name"),
        )
        if observed_mapping != expected_mapping:
            errors.append(f"{prefix}: stable subject mapping changed")
        qualification = entry.get("qualification", {})
        if not isinstance(qualification, dict):
            errors.append(f"{prefix}: qualification must be an object")
            qualification = {}
        steps = qualification.get("steps", [])
        if not isinstance(steps, list):
            errors.append(f"{prefix}: qualification steps must be a list")
            steps = []
        step_ids = [
            step.get("id") if isinstance(step, dict) else None for step in steps
        ]
        if not all(isinstance(step_id, str) and step_id for step_id in step_ids) or len(
            step_ids
        ) != len(set(step_ids)):
            errors.append(f"{prefix}: qualification step IDs must be unique")
        actions = [
            step.get("action") if isinstance(step, dict) else None for step in steps
        ]
        write_status = qualification.get("write_qualification_status")
        if subject_id == "gnosissafeproxy":
            if write_status != "not_applicable_without_singleton_implementation":
                errors.append(f"{prefix}: write qualification must be not_applicable")
            if actions != ["observe"]:
                errors.append(f"{prefix}: only the selector observation is allowed")
        else:
            if write_status != "executed":
                errors.append(f"{prefix}: write qualification must be executed")
            if "transact" not in actions or "observe" not in actions:
                errors.append(f"{prefix}: executed qualification needs write and read")
        for step in steps:
            if not isinstance(step, dict):
                errors.append(f"{prefix}: each qualification step must be an object")
                continue
            step_prefix = f"{prefix}:{step.get('id', '<missing>')}"
            if step.get("action") == "observe":
                if not isinstance(step.get("observer"), str):
                    errors.append(f"{step_prefix}: observer is required")
                expectation = step.get("expect")
                if (
                    not isinstance(expectation, dict)
                    or len(expectation) != 1
                    or not set(expectation)
                    <= {
                        "equals",
                        "equals_role",
                        "sequence_first_equals",
                        "greater_than",
                    }
                ):
                    errors.append(f"{step_prefix}: invalid observation expectation")
            elif step.get("action") == "transact":
                if (
                    not isinstance(step.get("function"), str)
                    or not isinstance(step.get("expect_success"), bool)
                    or not isinstance(step.get("arguments", []), list)
                ):
                    errors.append(f"{step_prefix}: invalid transaction schema")
            else:
                errors.append(f"{step_prefix}: action must be observe or transact")
            if not isinstance(step.get("arguments", []), list):
                errors.append(f"{step_prefix}: arguments must be a list")

        try:
            source = _repository_path(root, entry["source_path"])
            profile_path = _repository_path(root, entry["profile_path"])
        except (KeyError, TypeError, ValueError) as error:
            errors.append(f"{prefix}: {error}")
            continue
        source_paths.add(entry["source_path"])
        profile_paths.add(entry["profile_path"])
        for label, path, expected in (
            ("source", source, entry.get("source_sha256")),
            ("profile", profile_path, entry.get("profile_sha256")),
        ):
            if not path.is_file():
                errors.append(f"{prefix}: {label} path is not a file")
            elif _file_digest(path) != expected:
                errors.append(f"{prefix}: {label} SHA-256 mismatch")
        if errors and any(item.startswith(prefix) for item in errors):
            continue

        profile = load_contract_profile(profile_path)
        for key in ("compiler", "contract_name", "contract_id"):
            expected = entry["subject_id"] if key == "contract_id" else entry[key]
            if profile.get(key) != expected:
                errors.append(
                    f"{prefix}: profile {key} {profile.get(key)!r} != {expected!r}"
                )
        if profile.get("source") != entry["source_path"]:
            errors.append(f"{prefix}: profile source path mismatch")
        if profile.get("deployment", {}).get("constructor_args", []) != entry.get(
            "constructor_args", []
        ):
            errors.append(f"{prefix}: constructor args do not match profile")
        try:
            abi = compile_profile_abi(profile)
            abi_errors = validate_profile_abi(profile, abi)
            errors.extend(f"{prefix}: ABI {error}" for error in abi_errors)
        except Exception as error:
            errors.append(f"{prefix}: compile/ABI validation failed: {error}")
            continue
        if qualify:
            qualification_errors = _qualify_subject(entry, root)
            errors.extend(qualification_errors)
            if not qualification_errors:
                qualified += 1

    actual_sources = {
        path.relative_to(root).as_posix()
        for path in (root / "experiment-data" / "subjects").rglob("*.sol")
    }
    actual_profiles = {
        path.relative_to(root).as_posix()
        for path in (root / "code" / "configs" / "contracts").glob("*.yaml")
    }
    if source_paths != actual_sources:
        errors.append("subject source manifest/disk inventory is not bidirectional")
    if profile_paths != actual_profiles:
        errors.append("subject profile manifest/disk inventory is not bidirectional")

    return {
        "schema_version": 1,
        "status": "pass" if not errors else "fail",
        "subject_count": len(entries),
        "qualified_subject_count": qualified if qualify else None,
        "errors": errors,
    }


def _validate_integrity(
    artifact: dict[str, Any],
    root: Path,
    errors: list[str],
) -> None:
    artifact_id = artifact.get("artifact_id", "<missing>")
    try:
        path = _repository_path(root, artifact["path"])
    except (KeyError, TypeError, ValueError) as error:
        errors.append(f"{artifact_id}: {error}")
        return
    kind = artifact.get("kind")
    if kind == "file":
        if not path.is_file():
            errors.append(f"{artifact_id}: missing file {artifact.get('path')}")
        elif _file_digest(path) != artifact.get("sha256"):
            errors.append(f"{artifact_id}: file SHA-256 mismatch")
    elif kind == "directory":
        if not path.is_dir():
            errors.append(f"{artifact_id}: missing directory {artifact.get('path')}")
        else:
            digest, count = _tree_digest(path)
            if digest != artifact.get("sha256_tree"):
                errors.append(f"{artifact_id}: directory tree SHA-256 mismatch")
            if count != artifact.get("file_count"):
                errors.append(f"{artifact_id}: directory file_count mismatch")
    else:
        errors.append(f"{artifact_id}: kind must be file or directory")


def _validate_dag(artifacts: list[dict[str, Any]], errors: list[str]) -> None:
    ids = [artifact.get("artifact_id") for artifact in artifacts]
    if len(ids) != len(set(ids)):
        errors.append("result artifact IDs must be unique")
        return
    graph = {
        artifact["artifact_id"]: artifact.get("upstream", [])
        for artifact in artifacts
        if artifact.get("artifact_id")
    }
    for artifact_id, upstream in graph.items():
        missing = set(upstream) - set(graph)
        if missing:
            errors.append(f"{artifact_id}: unknown upstream IDs {sorted(missing)!r}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            errors.append(f"lineage cycle detected at {node}")
            return
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph.get(node, []):
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for artifact_id in graph:
        visit(artifact_id)


def _validate_canonical_matrix(root: Path, errors: list[str]) -> None:
    matrix_root = (
        root / "experiment-data" / "results" / "canonical" / "mytoken_mr6_small"
    )
    summary = _read_json(matrix_root / "summary.json")
    matrix = _read_json(matrix_root / "detection_matrix.json")
    expected_cells = {
        (mr_id, subject_id)
        for mr_id in EXPECTED_MR_IDS
        for subject_id in ["original", *EXPECTED_MUTANT_IDS]
    }
    cells = summary.get("cells", [])
    identities = {(cell.get("mr_id"), cell.get("subject_id")) for cell in cells}
    if identities != expected_cells or len(cells) != 12:
        errors.append("canonical matrix must contain exactly 3 x (baseline + 3)")
    if summary.get("mr_ids") != EXPECTED_MR_IDS:
        errors.append("canonical summary MR identities changed")
    if matrix.get("mr_ids") != EXPECTED_MR_IDS:
        errors.append("canonical JSON matrix MR identities changed")
    if matrix.get("mutant_ids") != EXPECTED_MUTANT_IDS:
        errors.append("canonical JSON matrix mutant identities changed")
    if summary.get("baseline_eligible") is not True:
        errors.append("canonical summary baseline_eligible must be true")
    if summary.get("indeterminate_mutants") != []:
        errors.append("canonical summary indeterminate_mutants must be empty")

    for cell in cells:
        mr_id = cell.get("mr_id")
        subject_id = cell.get("subject_id")
        evidence = _safe_child_path(
            matrix_root,
            str(cell.get("evidence", "")),
        )
        if not evidence.is_file():
            errors.append(f"canonical cell evidence missing: {mr_id}/{subject_id}")
            continue
        raw = _read_json(evidence)
        if raw.get("required_predicates_complete") is not True:
            errors.append(f"canonical predicates incomplete: {mr_id}/{subject_id}")
        try:
            expected_detection = canonical_cell_detection(raw)
        except ValueError:
            errors.append(
                f"canonical cell is indeterminate, not survive: {mr_id}/{subject_id}"
            )
            continue
        verdict = raw["oracle_verdict"]
        if (
            cell.get("verdict") != verdict
            or cell.get("detection") != expected_detection
        ):
            errors.append(f"canonical summary/cell mismatch: {mr_id}/{subject_id}")
        if subject_id == "original":
            if verdict != "pass":
                errors.append(f"canonical baseline must pass: {mr_id}")
        elif matrix["matrix"][mr_id][subject_id] != expected_detection:
            errors.append(
                f"canonical detection matrix/cell mismatch: {mr_id}/{subject_id}"
            )

    with (matrix_root / "detection_matrix.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = reader.fieldnames
    if [row["mr_id"] for row in rows] != EXPECTED_MR_IDS:
        errors.append("canonical CSV matrix MR identities changed")
    if fieldnames != ["mr_id", *EXPECTED_MUTANT_IDS]:
        errors.append("canonical CSV matrix mutant identities changed")
    for row in rows:
        mr_id = row["mr_id"]
        for mutant_id in EXPECTED_MUTANT_IDS:
            json_value = matrix["matrix"][mr_id][mutant_id]
            if (
                json_value not in {0, 1}
                or row[mutant_id] not in {"0", "1"}
                or int(row[mutant_id]) != json_value
            ):
                errors.append("canonical CSV/JSON matrix mismatch")
    killed = {
        mutant_id
        for mutant_id in EXPECTED_MUTANT_IDS
        if any(matrix["matrix"][mr_id][mutant_id] == 1 for mr_id in EXPECTED_MR_IDS)
    }
    if set(summary.get("killed_mutants", [])) != killed:
        errors.append("canonical killed-mutant summary is inconsistent")
    if set(summary.get("surviving_mutants", [])) != set(EXPECTED_MUTANT_IDS) - killed:
        errors.append("canonical surviving-mutant summary is inconsistent")
    expected_survivors = {
        mutant_id
        for mutant_id in EXPECTED_MUTANT_IDS
        if all(matrix["matrix"][mr_id][mutant_id] == 0 for mr_id in EXPECTED_MR_IDS)
    }
    if set(summary.get("surviving_mutants", [])) != expected_survivors:
        errors.append("surviving mutants must pass every canonical MR")


def canonical_cell_detection(raw: dict[str, Any]) -> int:
    """Return kill/survive only for complete cells; reject indeterminate cells."""

    verdict = raw.get("oracle_verdict")
    if (
        raw.get("execution_status") != "completed"
        or verdict not in {"pass", "violation"}
        or raw.get("errors") != []
        or raw.get("required_predicates_complete") is not True
    ):
        raise ValueError(
            "error, incomplete-predicate, and None-verdict cells are indeterminate"
        )
    return int(verdict == "violation")


def _validate_repetition_score_optimizer_chain(
    root: Path,
    errors: list[str],
) -> None:
    canonical = (
        root / "experiment-data" / "results" / "canonical" / "mytoken_optimization"
    )
    repetitions_root = canonical / "repetitions"
    summary = _read_json(repetitions_root / "summary.json")
    if summary.get("mr_ids") != EXPECTED_MR_IDS:
        errors.append("repetition-chain MR identities changed")
    if summary.get("mutant_ids") != EXPECTED_MUTANT_IDS:
        errors.append("repetition-chain mutant identities changed")
    repetitions = summary.get("repetitions_per_cell")
    if repetitions != 10 or summary.get("total_runs") != 120:
        errors.append("repetition chain must contain exactly 120 runs")

    records: dict[tuple[str, str, int], dict[str, Any]] = {}
    run_ids: set[str] = set()
    evidence_paths: set[str] = set()
    for item in summary.get("runs", []):
        run_id = item.get("run_id")
        evidence_raw = str(item.get("evidence", ""))
        evidence = _safe_child_path(repetitions_root, evidence_raw)
        if not isinstance(run_id, str) or run_id in run_ids:
            errors.append(f"duplicate or invalid repetition run_id: {run_id!r}")
        else:
            run_ids.add(run_id)
        if evidence_raw in evidence_paths:
            errors.append(f"duplicate repetition evidence path: {evidence_raw!r}")
        evidence_paths.add(evidence_raw)
        if not evidence.is_file():
            errors.append(f"repetition evidence is missing: {run_id}")
            continue
        raw = _read_json(evidence)
        key = (
            raw.get("mr_id"),
            raw.get("subject_id"),
            raw.get("repetition"),
        )
        if key in records:
            errors.append(f"duplicate repetition run identity: {key!r}")
        records[key] = raw
        expected_run_id = (
            f"{raw.get('mr_id')}__{raw.get('subject_id')}__{raw.get('repetition'):02}"
            if isinstance(raw.get("repetition"), int)
            else None
        )
        if run_id != expected_run_id or raw.get("run_id") != expected_run_id:
            errors.append(f"repetition run_id/identity mismatch: {run_id!r}")
        try:
            canonical_cell_detection(raw)
        except ValueError:
            errors.append(f"indeterminate repetition run: {run_id}")
        if raw.get("required_predicates_complete") is not True:
            errors.append(f"incomplete predicates: {run_id}")
        if any(
            item.get(field) != raw.get(field)
            for field in (
                "mr_id",
                "subject_id",
                "repetition",
                "execution_status",
                "oracle_verdict",
                "errors",
                "required_predicates_complete",
            )
        ):
            errors.append(f"repetition summary/raw mismatch: {run_id}")
    expected_keys = {
        (mr_id, subject_id, repetition)
        for mr_id in EXPECTED_MR_IDS
        for subject_id in ["original", *EXPECTED_MUTANT_IDS]
        for repetition in range(1, 11)
    }
    if set(records) != expected_keys:
        errors.append("repetition run identities are incomplete or unexpected")

    observed_tck: dict[tuple[str, str], int] = {}
    for mr_id in EXPECTED_MR_IDS:
        for repetition in range(1, 11):
            baseline = records.get((mr_id, "original", repetition), {})
            if baseline.get("oracle_verdict") != "pass":
                errors.append(f"repetition baseline must pass: {mr_id}/{repetition}")
        for mutant_id in EXPECTED_MUTANT_IDS:
            observed_tck[(mr_id, mutant_id)] = sum(
                records.get((mr_id, mutant_id, repetition), {}).get("oracle_verdict")
                == "violation"
                for repetition in range(1, 11)
            )

    score = _read_json(canonical / "scores" / "kill_vectors.json")
    if score.get("mr_ids") != EXPECTED_MR_IDS:
        errors.append("score-chain MR identities changed")
    if score.get("mutant_ids") != EXPECTED_MUTANT_IDS:
        errors.append("score-chain mutant identities changed")
    if score.get("raw_runs_consumed") != 120:
        errors.append("score chain must consume all 120 raw runs")
    tau = score.get("tau")
    if isinstance(tau, bool) or not isinstance(tau, (int, float)) or not 0 <= tau <= 1:
        errors.append("score tau must be a number in [0, 1]")
        tau = 0.1
    score_cells = score.get("cells", [])
    score_identities = [
        (cell.get("mr_id"), cell.get("mutant_id")) for cell in score_cells
    ]
    expected_score_identities = {
        (mr_id, mutant_id)
        for mr_id in EXPECTED_MR_IDS
        for mutant_id in EXPECTED_MUTANT_IDS
    }
    if (
        len(score_cells) != 9
        or len(score_identities) != len(set(score_identities))
        or set(score_identities) != expected_score_identities
    ):
        errors.append("score chain must contain exactly 9 unique cell identities")
    for cell in score_cells:
        key = (cell.get("mr_id"), cell.get("mutant_id"))
        tck = observed_tck.get(key)
        if cell.get("TCE") != 10 or cell.get("TCK") != tck:
            errors.append(f"score/repetition count mismatch: {key!r}")
            continue
        expected_ratio = tck / 10
        if cell.get("detection_ratio") != expected_ratio:
            errors.append(f"score detection ratio mismatch: {key!r}")
        expected_kill = int((tck / 10) >= tau)
        if cell.get("tau") != tau:
            errors.append(f"score cell tau mismatch: {key!r}")
        if cell.get("K_ik") != expected_kill:
            errors.append(f"score kill threshold mismatch: {key!r}")
        if score["kill_vectors"][key[0]][key[1]] != expected_kill:
            errors.append(f"kill-vector cell mismatch: {key!r}")
    for mr_id in EXPECTED_MR_IDS:
        vector = score.get("kill_vectors", {}).get(mr_id, {})
        if set(vector) != set(EXPECTED_MUTANT_IDS) or any(
            value not in {0, 1} for value in vector.values()
        ):
            errors.append(f"invalid score kill vector: {mr_id}")
            continue
        expected_score = sum(vector.values()) / len(EXPECTED_MUTANT_IDS)
        if score.get("mutation_scores", {}).get(mr_id) != expected_score:
            errors.append(f"mutation score does not match kill vector: {mr_id}")

    optimization = _read_json(canonical / "algorithm1" / "optimization.json")
    if optimization.get("mr_ids") != EXPECTED_MR_IDS:
        errors.append("optimizer MR identities changed")
    if optimization.get("mutant_ids") != EXPECTED_MUTANT_IDS:
        errors.append("optimizer mutant identities changed")
    if optimization.get("kill_vectors") != score.get("kill_vectors"):
        errors.append("optimizer kill vectors do not match score lineage")
    if optimization.get("claim_scope") != "control_only":
        errors.append("optimizer claim scope must remain control_only")
    scenario = yaml.safe_load(
        (
            root
            / "code"
            / "configs"
            / "experiments"
            / "mytoken_canonical_optimization.yaml"
        ).read_text(encoding="utf-8")
    )
    parameters = scenario["parameters"]
    if optimization.get("scenario_id") != scenario["scenario_id"]:
        errors.append("optimizer scenario_id changed")
    if parameters.get("tau") != tau:
        errors.append("optimizer config tau differs from score evidence")
    config = MPSCConfig(
        tau=parameters["tau"],
        tau_c=parameters["tau_c"],
        min_set_size=parameters["min_set_size"],
        ms_weight=parameters["ms_weight"],
        ds_weight=parameters["ds_weight"],
    )
    kill_vectors = {
        mr_id: KillVector(
            mr_id=mr_id,
            kills={
                mutant_id: bool(score["kill_vectors"][mr_id][mutant_id])
                for mutant_id in EXPECTED_MUTANT_IDS
            },
        )
        for mr_id in EXPECTED_MR_IDS
    }
    expected_pairwise = {
        left: {
            right: compute_jaccard_distance(
                kill_vectors[left],
                kill_vectors[right],
            )
            for right in EXPECTED_MR_IDS
        }
        for left in EXPECTED_MR_IDS
    }
    expected_difference = {
        mr_id: compute_difference_score(
            mr_id,
            EXPECTED_MR_IDS,
            kill_vectors,
        )
        for mr_id in EXPECTED_MR_IDS
    }
    relations = [_optimizer_relation(mr_id) for mr_id in reversed(EXPECTED_MR_IDS)]
    expected_trace = optimize_mr_category_with_trace(
        relations,
        kill_vectors,
        config,
    )
    expected_combined = {
        mr_id: (
            config.ms_weight * expected_trace["mutation_scores"][mr_id]
            + config.ds_weight * expected_difference[mr_id]
        )
        for mr_id in EXPECTED_MR_IDS
    }
    if optimization.get("pairwise_mrd") != expected_pairwise:
        errors.append("optimizer pairwise MRD does not recompute")
    if optimization.get("initial_difference_scores") != expected_difference:
        errors.append("optimizer difference scores do not recompute")
    if optimization.get("initial_combined_scores") != expected_combined:
        errors.append("optimizer combined scores do not recompute")
    if optimization.get("algorithm_1") != expected_trace:
        errors.append("optimizer Algorithm 1 trajectory/parameters do not recompute")


def _optimizer_relation(mr_id: str) -> MetamorphicRelation:
    return MetamorphicRelation(
        mr_id=mr_id,
        category="MR6.amount_transform",
        target_operation="sendCoin",
        input_relation=InputRelation(
            description="canonical amount transformation",
            transform=mr_id,
        ),
        output_relation=OutputRelation(
            description="mr6_amount",
            check_type="mr6_amount",
        ),
    )


def _validate_processed_mapping(
    index: dict[str, Any],
    root: Path,
    errors: list[str],
) -> None:
    mappings = index.get("processed_output_mappings", [])
    mapping_ids = [mapping.get("mapping_id") for mapping in mappings]
    if len(mapping_ids) != len(set(mapping_ids)) or set(mapping_ids) != set(
        EXPECTED_PROCESSED_MAPPINGS
    ):
        errors.append("processed mapping IDs must match the frozen 14-item set")
    for mapping in mappings:
        mapping_id = mapping.get("mapping_id", "<missing>")
        expected = EXPECTED_PROCESSED_MAPPINGS.get(mapping_id)
        if expected and (mapping.get("input"), mapping.get("output")) != expected:
            errors.append(f"{mapping_id}: frozen input/output mapping changed")
        for key in ("input", "output"):
            try:
                path = _repository_path(root, mapping[key])
            except (KeyError, TypeError, ValueError) as error:
                errors.append(f"{mapping_id}: {error}")
                continue
            if not path.is_file():
                errors.append(f"{mapping_id}: {key} file is missing")
        if not mapping.get("command"):
            errors.append(f"{mapping_id}: generation command is required")
        if not mapping.get("boundary"):
            errors.append(f"{mapping_id}: claim boundary is required")


def validate_results_evidence(
    index_path: str | Path,
    *,
    subject_manifest_path: str | Path,
    base_dir: str | Path = ".",
    qualify_subjects: bool = False,
) -> dict[str, Any]:
    """Validate hashes, lineage, processed mappings, and the canonical matrix."""

    root = Path(base_dir).resolve()
    errors: list[str] = []
    try:
        index = _read_json(Path(index_path))
    except (OSError, json.JSONDecodeError) as error:
        return {"status": "fail", "errors": [f"cannot read result index: {error}"]}
    if index.get("schema_version") != 1:
        errors.append("results evidence schema_version must equal 1")
    if index.get("index_id") != EXPECTED_INDEX_ID:
        errors.append("results evidence index_id changed")

    artifacts = index.get("artifacts", [])
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("result artifacts must be a non-empty list")
        artifacts = []
    artifact_rows = [artifact for artifact in artifacts if isinstance(artifact, dict)]
    if len(artifact_rows) != len(artifacts):
        errors.append("each result artifact must be an object")
    for artifact in artifact_rows:
        artifact_id = artifact.get("artifact_id", "<missing>")
        if not isinstance(artifact.get("upstream", []), list):
            errors.append(f"{artifact_id}: upstream must be a list")
            artifact["upstream"] = []
        evidence_class = artifact.get("evidence_class")
        if evidence_class not in EVIDENCE_CLASSES:
            errors.append(f"{artifact_id}: invalid evidence_class")
        if not artifact.get("verification_command"):
            errors.append(f"{artifact_id}: verification_command is required")
        _validate_integrity(artifact, root, errors)
    _validate_dag(artifact_rows, errors)

    by_id = {artifact.get("artifact_id"): artifact for artifact in artifact_rows}
    if set(by_id) != set(EXPECTED_ARTIFACT_LINEAGE) or len(artifacts) != 10:
        errors.append("result artifacts must match the frozen 10-node set")
    observed_edge_count = sum(
        len(artifact.get("upstream", [])) for artifact in artifact_rows
    )
    if observed_edge_count != 9:
        errors.append("result lineage must contain exactly 9 edges")
    for artifact_id, (
        evidence_class,
        upstream,
    ) in EXPECTED_ARTIFACT_LINEAGE.items():
        artifact = by_id.get(artifact_id)
        if artifact is None:
            errors.append(f"required result artifact is absent: {artifact_id}")
            continue
        if artifact.get("evidence_class") != evidence_class:
            errors.append(f"{artifact_id}: evidence class cannot be reclassified")
        if tuple(artifact.get("upstream", [])) != upstream:
            errors.append(f"{artifact_id}: frozen upstream edge set changed")

    validators = [
        ("canonical matrix", lambda: _validate_canonical_matrix(root, errors)),
        (
            "repetition/score/optimizer chain",
            lambda: _validate_repetition_score_optimizer_chain(root, errors),
        ),
        (
            "processed mappings",
            lambda: _validate_processed_mapping(index, root, errors),
        ),
    ]
    for label, validator in validators:
        try:
            validator()
        except (
            KeyError,
            AttributeError,
            TypeError,
            ValueError,
            OSError,
            json.JSONDecodeError,
        ) as error:
            errors.append(f"{label} validation failed: {error}")
    try:
        subject_result = validate_subject_manifest(
            subject_manifest_path,
            base_dir=root,
            qualify=qualify_subjects,
        )
    except (
        KeyError,
        AttributeError,
        TypeError,
        ValueError,
        OSError,
        json.JSONDecodeError,
    ) as error:
        subject_result = {
            "status": "fail",
            "subject_count": None,
            "qualified_subject_count": None,
            "errors": [f"subject manifest validation failed: {error}"],
        }
    errors.extend(f"subjects: {error}" for error in subject_result["errors"])
    return {
        "schema_version": 1,
        "status": "pass" if not errors else "fail",
        "artifact_count": len(artifacts),
        "lineage_edge_count": sum(
            len(artifact.get("upstream", [])) for artifact in artifact_rows
        ),
        "processed_mapping_count": len(index.get("processed_output_mappings", [])),
        "subject_count": subject_result.get("subject_count"),
        "qualified_subject_count": subject_result.get("qualified_subject_count"),
        "canonical_matrix_dimensions": {
            "mr_count": 3,
            "baseline_count": 1,
            "mutant_count": 3,
            "cell_count": 12,
        },
        "errors": errors,
    }
