"""Validation for a frozen, provenance-aware mutant corpus."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

DEFAULT_CORPUS = Path("code/configs/experiments/mytoken_canonical_mutants.yaml")
DEFAULT_PUBLIC_CORPUS = Path("experiment-data/mutants/corpus_manifest.json")
DEFAULT_PUBLIC_MUTANTS_ROOT = Path("experiment-data/mutants")
PUBLIC_CORPUS_ID = "mpsc_controls_v1"
PUBLIC_SCHEMA_DOCUMENTATION = "README.md"
QUALIFICATION_COMMAND = "uv run mpsc verify-mutant-corpus --qualify"
PUBLIC_RECORD_DEFAULTS = {
    "mutation": {"operator_basis": "textual_change"},
    "provenance": {
        "method": "documented_process",
        "origin": "provided_records",
    },
}
PUBLIC_QUALIFICATION_ENVIRONMENT = {
    "verified_on": "",
    "python": "3.11",
    "py_solc_x": "2.0.5",
    "eth_tester": "0.13.0b1",
    "py_evm": "0.12.1b1",
    "web3": "7.16.0",
    "compile_command": QUALIFICATION_COMMAND,
    "deployment_condition": (
        "fresh eth-tester/PyEVMBackend chain, profile-compatible constructor "
        "arguments, default funded account as deployer"
    ),
}
PUBLIC_SUBJECTS = (
    "MyToken",
    "BecToken",
    "PERSONAL_BANK",
    "Rubixi",
    "GnosisSafeProxy",
)
PUBLIC_SUBJECT_COUNTS = {
    "MyToken": 53,
    "Rubixi": 172,
    "BecToken": 151,
    "GnosisSafeProxy": 76,
    "PERSONAL_BANK": 83,
}
PUBLIC_EQUIVALENT_COUNTS = {
    "MyToken": 4,
    "Rubixi": 19,
    "BecToken": 9,
    "GnosisSafeProxy": 6,
    "PERSONAL_BANK": 2,
}
CANONICAL_RECORD_IDS = frozenset(
    {
        "MyToken::MUT-01",
        "MyToken::MUT-07",
        "MyToken::MUT-08",
    }
)
QUALIFICATION_STATUSES = frozenset(
    {"verified_pass", "verified_fail", "not_applicable", "not_verified"}
)
EQUIVALENCE_STATUSES = frozenset(
    {"equivalent", "non_equivalent", "unknown_not_reviewed"}
)


def validate_frozen_corpus(
    config_path: str | Path = DEFAULT_CORPUS,
    *,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Validate frozen hashes and eligibility evidence."""

    path = Path(config_path)
    base = Path(base_dir) if base_dir is not None else Path()
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("hash_canonicalization") != "lf":
        raise ValueError("corpus hash_canonicalization must be 'lf'")
    subject = config["subject"]
    subject_path = base / subject["path"]
    subject_actual = canonical_source_sha256(subject_path)
    subject_matches = subject_actual == subject["sha256"]

    records = []
    seen_ids: set[str] = set()
    for item in config["mutants"]:
        mutant_id = item["mutant_id"]
        if mutant_id in seen_ids:
            raise ValueError(f"duplicate mutant ID: {mutant_id}")
        seen_ids.add(mutant_id)

        mutant_path = base / item["path"]
        actual_hash = canonical_source_sha256(mutant_path)
        raw_hash = _raw_sha256(mutant_path)
        manifest_path = base / item["manifest"]
        manifest_entry = json.loads(manifest_path.read_text(encoding="utf-8"))
        frozen_matches = actual_hash == item["sha256"]
        hash_matches = actual_hash == manifest_entry.get("mutant_sha256")
        eligible = bool(
            manifest_entry.get("generation_success")
            and manifest_entry.get("compile_success")
        )
        declared_eligible = item["eligibility_status"] == "eligible"
        eligible = frozen_matches and eligible and declared_eligible
        records.append(
            {
                "mutant_id": mutant_id,
                "path": item["path"],
                "frozen_sha256": item["sha256"],
                "actual_sha256": actual_hash,
                "raw_sha256": raw_hash,
                "frozen_hash_matches": frozen_matches,
                "manifest": item["manifest"],
                "declared_sha256": manifest_entry.get("mutant_sha256"),
                "hash_matches": hash_matches,
                "generation_success": manifest_entry.get("generation_success"),
                "compile_success": manifest_entry.get("compile_success"),
                "origin": item["origin"],
                "eligibility_status": "eligible" if eligible else "ineligible",
            }
        )

    eligible_count = sum(
        record["eligibility_status"] == "eligible" for record in records
    )
    return {
        "schema_version": 2,
        "corpus_id": config["corpus_id"],
        "config_path": path.as_posix(),
        "frozen_at_commit": config["frozen_at_commit"],
        "hash_canonicalization": config["hash_canonicalization"],
        "subject": {
            "id": subject["id"],
            "path": subject["path"],
            "frozen_sha256": subject["sha256"],
            "actual_sha256": subject_actual,
            "raw_sha256": _raw_sha256(subject_path),
            "frozen_hash_matches": subject_matches,
        },
        "eligibility_policy": config["eligibility_policy"],
        "mutant_count": len(records),
        "eligible_count": eligible_count,
        "ineligible_count": len(records) - eligible_count,
        "hash_mismatch_count": sum(not record["hash_matches"] for record in records),
        "valid": subject_matches and eligible_count == len(records),
        "mutants": records,
    }


def write_corpus_validation(
    output_path: str | Path,
    config_path: str | Path = DEFAULT_CORPUS,
) -> dict[str, Any]:
    """Validate and save a deterministic audit artifact."""

    report = validate_frozen_corpus(config_path)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def canonical_source_sha256(path: str | Path) -> str:
    """Hash source after portable LF newline normalization."""

    content = Path(path).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(content).hexdigest()


def _raw_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_repository_path(raw_path: Any, base_dir: Path) -> Path:
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError("path must be a non-empty string")
    posix = PurePosixPath(raw_path)
    if posix.is_absolute() or ".." in posix.parts or "\\" in raw_path:
        raise ValueError(f"path is not normalized repository-relative: {raw_path}")
    resolved = (base_dir / Path(*posix.parts)).resolve()
    base_resolved = base_dir.resolve()
    if resolved != base_resolved and base_resolved not in resolved.parents:
        raise ValueError(f"path escapes repository root: {raw_path}")
    return resolved


def _require_nonempty(
    value: Any,
    field: str,
    prefix: str,
    errors: list[str],
) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{prefix}.{field} must be a non-empty string")


def validate_public_corpus(
    manifest_path: str | Path = DEFAULT_PUBLIC_CORPUS,
    *,
    base_dir: str | Path = ".",
    mutants_root: str | Path = DEFAULT_PUBLIC_MUTANTS_ROOT,
) -> dict[str, Any]:
    """Validate the complete public engineering-mutant inventory.

    This verifier is deliberately read-only. It checks declared identities,
    paths, LF-normalized source hashes, classification and qualification
    records, but it never rewrites a mutant or its evidence.
    """

    base = Path(base_dir)
    manifest = Path(manifest_path)
    if not manifest.is_absolute():
        manifest = base / manifest
    errors: list[str] = []
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {
            "status": "fail",
            "manifest": str(manifest),
            "errors": [f"cannot read corpus manifest: {error}"],
        }
    if not isinstance(payload, dict):
        return {
            "status": "fail",
            "manifest": str(manifest),
            "errors": ["corpus manifest root must be an object"],
        }

    if payload.get("schema_version") != 1:
        errors.append("schema_version must equal 1")
    if payload.get("corpus_id") != PUBLIC_CORPUS_ID:
        errors.append(f"corpus_id must equal {PUBLIC_CORPUS_ID!r}")
    for removed_field in ("evidence_class", "claim_boundary"):
        if removed_field in payload:
            errors.append(f"{removed_field} is not supported by the corpus schema")
    if payload.get("hash_canonicalization") != "lf":
        errors.append("hash_canonicalization must equal 'lf'")
    if payload.get("record_defaults") != PUBLIC_RECORD_DEFAULTS:
        errors.append("record_defaults must match the supported corpus defaults")
    if payload.get("schema_documentation") != PUBLIC_SCHEMA_DOCUMENTATION:
        errors.append(
            f"schema_documentation must equal {PUBLIC_SCHEMA_DOCUMENTATION!r}"
        )
    else:
        schema_path = _safe_repository_path(PUBLIC_SCHEMA_DOCUMENTATION, base)
        if not schema_path.is_file():
            errors.append("schema_documentation path does not exist")

    qualification_environment = payload.get("qualification_environment", {})
    if not isinstance(qualification_environment, dict):
        qualification_environment = {}
        errors.append("qualification_environment must be an object")
    for field, expected in PUBLIC_QUALIFICATION_ENVIRONMENT.items():
        if qualification_environment.get(field) != expected:
            errors.append(f"qualification_environment.{field} must equal {expected!r}")

    declared_counts = payload.get("subject_counts")
    if not isinstance(declared_counts, dict):
        declared_counts = {}
        errors.append("subject_counts must be an object")
    if set(declared_counts) != set(PUBLIC_SUBJECTS):
        errors.append("subject_counts must list exactly the five corpus subjects")
    for subject, count in declared_counts.items():
        if not isinstance(count, int) or count < 0:
            errors.append(f"subject_counts.{subject} must be a non-negative integer")
    if declared_counts != PUBLIC_SUBJECT_COUNTS:
        errors.append(
            "subject_counts must match the frozen aggregate counts: "
            f"{PUBLIC_SUBJECT_COUNTS}"
        )

    declared_equivalent_counts = payload.get("equivalent_counts")
    if declared_equivalent_counts != PUBLIC_EQUIVALENT_COUNTS:
        errors.append(
            "equivalent_counts must match the frozen aggregate counts: "
            f"{PUBLIC_EQUIVALENT_COUNTS}"
        )
    declared_non_equivalent_counts = payload.get("non_equivalent_counts")
    expected_non_equivalent_counts = {
        subject: PUBLIC_SUBJECT_COUNTS[subject] - PUBLIC_EQUIVALENT_COUNTS[subject]
        for subject in PUBLIC_SUBJECTS
    }
    if declared_non_equivalent_counts != expected_non_equivalent_counts:
        errors.append("non_equivalent_counts must match total minus equivalent counts")

    records = payload.get("mutants")
    if not isinstance(records, list):
        records = []
        errors.append("mutants must be an array")

    seen_record_ids: set[str] = set()
    seen_identities: set[tuple[str, str]] = set()
    seen_paths: set[str] = set()
    actual_counts = {subject: 0 for subject in PUBLIC_SUBJECTS}
    actual_equivalent_counts = {subject: 0 for subject in PUBLIC_SUBJECTS}
    declared_paths: set[str] = set()

    for index, record in enumerate(records):
        prefix = f"mutants[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{prefix} must be an object")
            continue
        record_id = record.get("record_id")
        subject = record.get("subject")
        mutant_id = record.get("mutant_id")
        for field, value in (
            ("record_id", record_id),
            ("subject", subject),
            ("mutant_id", mutant_id),
        ):
            _require_nonempty(value, field, prefix, errors)
        if isinstance(record_id, str):
            if record_id in seen_record_ids:
                errors.append(f"duplicate record_id: {record_id}")
            seen_record_ids.add(record_id)
        if isinstance(subject, str) and isinstance(mutant_id, str):
            identity = (subject, mutant_id)
            if identity in seen_identities:
                errors.append(f"duplicate mutant identity: {subject}/{mutant_id}")
            seen_identities.add(identity)
            if record_id != f"{subject}::{mutant_id}":
                errors.append(f"{prefix}.record_id must equal subject::mutant_id")
            if subject in actual_counts:
                actual_counts[subject] += 1
            else:
                errors.append(f"{prefix}.subject is not a declared subject")
        if "evidence_class" in record:
            errors.append(f"{prefix}.evidence_class is not supported")
        source = record.get("source", {})
        mutant = record.get("mutant", {})
        for label, item in (("source", source), ("mutant", mutant)):
            if not isinstance(item, dict):
                errors.append(f"{prefix}.{label} must be an object")
                continue
            raw_path = item.get("path")
            digest = item.get("sha256")
            _require_nonempty(digest, f"{label}.sha256", prefix, errors)
            try:
                resolved = _safe_repository_path(raw_path, base)
            except ValueError as error:
                errors.append(f"{prefix}.{label}.path: {error}")
                continue
            if label == "mutant":
                if raw_path in seen_paths:
                    errors.append(f"duplicate mutant path: {raw_path}")
                seen_paths.add(raw_path)
                declared_paths.add(raw_path)
            if not resolved.is_file():
                errors.append(f"{prefix}.{label}.path does not exist: {raw_path}")
                continue
            if canonical_source_sha256(resolved) != digest:
                errors.append(f"{prefix}.{label}.sha256 does not match: {raw_path}")
        if not isinstance(source, dict):
            source = {}
        if not isinstance(mutant, dict):
            mutant = {}

        mutation = record.get("mutation", {})
        if not isinstance(mutation, dict):
            errors.append(f"{prefix}.mutation must be an object")
            mutation = {}
        else:
            if "operator_basis" in mutation:
                errors.append(
                    f"{prefix}.mutation.operator_basis must use record_defaults"
                )
            for field in (
                "operator",
                "description",
                "original_text",
                "mutated_text",
            ):
                _require_nonempty(
                    mutation.get(field),
                    f"mutation.{field}",
                    prefix,
                    errors,
                )
            line_number = mutation.get("line")
            if (
                not isinstance(line_number, int)
                or isinstance(line_number, bool)
                or line_number <= 0
            ):
                errors.append(f"{prefix}.mutation.line must be a positive integer")
            else:
                _validate_mutation_line(
                    source,
                    mutant,
                    mutation,
                    base,
                    prefix,
                    errors,
                )
        provenance = record.get("provenance", {})
        if not isinstance(provenance, dict):
            errors.append(f"{prefix}.provenance must be an object")
        else:
            for field in ("origin", "method"):
                if field in provenance:
                    errors.append(
                        f"{prefix}.provenance.{field} must use record_defaults"
                    )
            _require_nonempty(
                provenance.get("source_record"),
                "provenance.source_record",
                prefix,
                errors,
            )
            try:
                source_record_path = _safe_repository_path(
                    provenance.get("source_record"), base
                )
                source_record = json.loads(
                    source_record_path.read_text(encoding="utf-8")
                )
            except (ValueError, OSError, json.JSONDecodeError) as error:
                errors.append(f"{prefix}.provenance.source_record: {error}")
            else:
                declared_qualification = record.get("qualification", {})
                declared_compile = (
                    declared_qualification.get("compile", {})
                    if isinstance(declared_qualification, dict)
                    else {}
                )
                declared_equivalence = (
                    declared_qualification.get("equivalence", {})
                    if isinstance(declared_qualification, dict)
                    else {}
                )
                declared_compile_status = (
                    declared_compile.get("status")
                    if isinstance(declared_compile, dict)
                    else None
                )
                expected_compile_success = {
                    "verified_pass": True,
                    "verified_fail": False,
                    "not_verified": None,
                    "not_applicable": None,
                }.get(declared_compile_status)
                expected_source_record = {
                    "authoritative_record": record_id,
                    "mutant_id": mutant_id,
                    "source_contract": source.get("path"),
                    "source_sha256": source.get("sha256"),
                    "mutant_file": mutant.get("path"),
                    "mutant_sha256": mutant.get("sha256"),
                    "operator": mutation.get("operator"),
                    "line": mutation.get("line"),
                    "original_text": mutation.get("original_text"),
                    "mutated_text": mutation.get("mutated_text"),
                    "compile_success": expected_compile_success,
                    "equivalence_status": (
                        declared_equivalence.get("status")
                        if isinstance(declared_equivalence, dict)
                        else None
                    ),
                }
                for field, expected in expected_source_record.items():
                    if source_record.get(field) != expected:
                        errors.append(
                            f"{prefix}.provenance.source_record.{field} "
                            "does not match the authoritative corpus record"
                        )

        qualification = record.get("qualification", {})
        if not isinstance(qualification, dict):
            errors.append(f"{prefix}.qualification must be an object")
            continue
        compile_record = qualification.get("compile", {})
        deploy_record = qualification.get("deploy", {})
        for label, item in (("compile", compile_record), ("deploy", deploy_record)):
            if not isinstance(item, dict):
                errors.append(f"{prefix}.qualification.{label} must be an object")
                continue
            if item.get("status") not in QUALIFICATION_STATUSES:
                errors.append(
                    f"{prefix}.qualification.{label}.status is not recognized"
                )
            _require_nonempty(
                item.get("rationale"),
                f"qualification.{label}.rationale",
                prefix,
                errors,
            )
        if isinstance(compile_record, dict):
            _require_nonempty(
                compile_record.get("compiler_version"),
                "qualification.compile.compiler_version",
                prefix,
                errors,
            )
        if isinstance(deploy_record, dict):
            _require_nonempty(
                deploy_record.get("backend"),
                "qualification.deploy.backend",
                prefix,
                errors,
            )
        stillborn = qualification.get("stillborn", {})
        if not isinstance(stillborn, dict):
            stillborn = {}
            errors.append(f"{prefix}.qualification.stillborn must be an object")
        if stillborn.get("status") not in {"false", "true", "unknown"}:
            errors.append(f"{prefix}.qualification.stillborn.status is not recognized")
        _require_nonempty(
            stillborn.get("rationale"),
            "qualification.stillborn.rationale",
            prefix,
            errors,
        )
        equivalence = qualification.get("equivalence", {})
        if not isinstance(equivalence, dict):
            equivalence = {}
            errors.append(f"{prefix}.qualification.equivalence must be an object")
        if equivalence.get("status") not in EQUIVALENCE_STATUSES:
            errors.append(
                f"{prefix}.qualification.equivalence.status is not recognized"
            )
        if "rationale" in equivalence:
            errors.append(
                f"{prefix}.qualification.equivalence.rationale is not supported"
            )
        if (
            subject in actual_equivalent_counts
            and equivalence.get("status") == "equivalent"
        ):
            actual_equivalent_counts[subject] += 1
        if isinstance(compile_record, dict) and isinstance(deploy_record, dict):
            _validate_qualification_logic(
                compile_record.get("status"),
                deploy_record.get("status"),
                stillborn.get("status"),
                prefix,
                errors,
            )

    root = Path(mutants_root)
    if not root.is_absolute():
        root = base / root
    base_resolved = base.resolve()
    root = root.resolve()
    try:
        root.relative_to(base_resolved)
    except ValueError:
        errors.append("mutants_root must be inside base_dir")
        disk_paths: set[str] = set()
    else:
        disk_paths = {
            path.resolve().relative_to(base_resolved).as_posix()
            for path in root.glob("*/*/*.sol")
            if path.is_file()
        }
    for path in sorted(disk_paths - declared_paths):
        errors.append(f"unlisted mutant file on disk: {path}")
    for path in sorted(declared_paths - disk_paths):
        errors.append(f"manifest mutant is outside the public corpus scan: {path}")

    if payload.get("total_mutants") != len(records):
        errors.append("total_mutants does not equal the number of manifest records")
    if payload.get("total_equivalent") != sum(actual_equivalent_counts.values()):
        errors.append("total_equivalent does not equal the equivalent record count")
    actual_non_equivalent_counts = {
        subject: actual_counts[subject] - actual_equivalent_counts[subject]
        for subject in PUBLIC_SUBJECTS
    }
    if payload.get("total_non_equivalent") != sum(
        actual_non_equivalent_counts.values()
    ):
        errors.append(
            "total_non_equivalent does not equal the non-equivalent record count"
        )
    if declared_counts != actual_counts:
        errors.append(
            "subject_counts mismatch: "
            f"declared={declared_counts}, actual={actual_counts}"
        )
    if declared_equivalent_counts != actual_equivalent_counts:
        errors.append(
            "equivalent_counts mismatch: "
            f"declared={declared_equivalent_counts}, "
            f"actual={actual_equivalent_counts}"
        )
    if declared_non_equivalent_counts != actual_non_equivalent_counts:
        errors.append(
            "non_equivalent_counts mismatch: "
            f"declared={declared_non_equivalent_counts}, "
            f"actual={actual_non_equivalent_counts}"
        )
    if len(disk_paths) != len(records):
        errors.append(
            "disk/manifest count mismatch: "
            f"disk={len(disk_paths)}, manifest={len(records)}"
        )
    canonical = payload.get("canonical_subset", {})
    canonical_ids = canonical.get("record_ids", [])
    if "evidence_class" in canonical:
        errors.append("canonical_subset.evidence_class is not supported")
    if (
        canonical.get("exact_membership") is not True
        or set(canonical_ids) != CANONICAL_RECORD_IDS
        or len(canonical_ids) != len(CANONICAL_RECORD_IDS)
    ):
        errors.append(
            "canonical_subset must contain exactly MyToken MUT-01/MUT-07/MUT-08"
        )
    if not set(canonical_ids).issubset(seen_record_ids):
        errors.append("canonical_subset includes an identity absent from the corpus")

    return {
        "status": "pass" if not errors else "fail",
        "manifest": manifest.relative_to(base).as_posix()
        if manifest.is_relative_to(base)
        else str(manifest),
        "declared_total": payload.get("total_mutants"),
        "disk_total": len(disk_paths),
        "subject_counts": actual_counts,
        "equivalent_counts": actual_equivalent_counts,
        "non_equivalent_counts": actual_non_equivalent_counts,
        "canonical_record_ids": sorted(canonical_ids),
        "errors": errors,
    }


def _validate_mutation_line(
    source: dict[str, Any],
    mutant: dict[str, Any],
    mutation: dict[str, Any],
    base: Path,
    prefix: str,
    errors: list[str],
) -> None:
    line_number = mutation["line"]
    for label, path_record, text_field in (
        ("source", source, "original_text"),
        ("mutant", mutant, "mutated_text"),
    ):
        raw_path = path_record.get("path")
        try:
            path = _safe_repository_path(raw_path, base)
            lines = path.read_text(encoding="utf-8").splitlines()
        except (ValueError, OSError, UnicodeDecodeError) as error:
            errors.append(f"{prefix}.mutation.{label}_line: {error}")
            continue
        if line_number > len(lines):
            errors.append(
                f"{prefix}.mutation.line {line_number} exceeds "
                f"{label} line count {len(lines)}"
            )
            continue
        expected_text = mutation.get(text_field)
        if (
            isinstance(expected_text, str)
            and expected_text not in lines[line_number - 1]
        ):
            errors.append(
                f"{prefix}.mutation.{text_field} is not present on "
                f"{label} line {line_number}"
            )


def _validate_qualification_logic(
    compile_status: Any,
    deploy_status: Any,
    stillborn_status: Any,
    prefix: str,
    errors: list[str],
) -> None:
    if compile_status == "verified_fail":
        if deploy_status == "verified_pass":
            errors.append(
                f"{prefix}.qualification.deploy cannot pass after compile failure"
            )
    elif compile_status != "verified_pass":
        if deploy_status == "verified_pass":
            errors.append(
                f"{prefix}.qualification.deploy cannot pass without verified compile"
            )
    if stillborn_status != "false":
        errors.append(
            f"{prefix}.qualification.stillborn.status must be 'false'"
        )


def qualify_public_corpus(
    manifest_path: str | Path = DEFAULT_PUBLIC_CORPUS,
    *,
    base_dir: str | Path = ".",
    mutants_root: str | Path = DEFAULT_PUBLIC_MUTANTS_ROOT,
) -> dict[str, Any]:
    """Re-run compile and minimal deployment qualification without writing files."""

    base = Path(base_dir)
    validation = validate_public_corpus(
        manifest_path,
        base_dir=base,
        mutants_root=mutants_root,
    )
    if validation["status"] != "pass":
        return {
            **validation,
            "qualification_status": "not_run_invalid_manifest",
            "qualification": [],
        }

    manifest = Path(manifest_path)
    if not manifest.is_absolute():
        manifest = base / manifest
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    for record in payload["mutants"]:
        item = _qualify_public_mutant(record, base)
        results.append(item)
        if item["compile_status"] != record["qualification"]["compile"]["status"]:
            errors.append(
                f"{record['record_id']} compile status changed: "
                f"declared={record['qualification']['compile']['status']}, "
                f"actual={item['compile_status']}"
            )
        if item["deploy_status"] != record["qualification"]["deploy"]["status"]:
            errors.append(
                f"{record['record_id']} deploy status changed: "
                f"declared={record['qualification']['deploy']['status']}, "
                f"actual={item['deploy_status']}"
            )
    return {
        **validation,
        "status": "pass" if not errors else "fail",
        "qualification_status": "pass" if not errors else "fail",
        "qualified_count": sum(
            item["compile_status"] == "verified_pass"
            and item["deploy_status"] == "verified_pass"
            for item in results
        ),
        "qualification": results,
        "errors": errors,
    }


def _qualify_public_mutant(record: dict[str, Any], base: Path) -> dict[str, Any]:
    from ..chain.local_backend import LocalChainBackend
    from ..solidity.compiler import compile_contract_solcx

    source_path = base / record["mutant"]["path"]
    compiler_version = record["qualification"]["compile"]["compiler_version"]
    compiled = compile_contract_solcx(source_path, compiler_version)
    result = {
        "record_id": record["record_id"],
        "compiler_version": compiler_version,
        "compile_status": "verified_pass" if compiled.success else "verified_fail",
        "compile_errors": compiled.errors,
        "deploy_status": "not_verified",
        "deployment_backend": "eth-tester/PyEVMBackend",
    }
    if not compiled.success:
        return result
    try:
        backend = LocalChainBackend()
        accounts = backend.get_accounts()
        constructor_args = (
            [accounts[1]] if record["subject"] == "GnosisSafeProxy" else []
        )
        receipt = backend.deploy(
            bytecode=compiled.bytecode,
            abi=compiled.abi,
            args=constructor_args,
            sender=accounts[0],
        )
        result["deploy_status"] = (
            "verified_pass"
            if receipt.success and receipt.contract_address
            else "verified_fail"
        )
    except Exception as error:  # pragma: no cover - environment-specific diagnostic
        result["deploy_status"] = "verified_fail"
        result["deploy_error"] = str(error)
    return result
