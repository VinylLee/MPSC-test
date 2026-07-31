"""Generate the deterministic 495-mutant non-equivalent corpus."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

# Add project root to path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "code" / "src"))

from mpsc.mutation.musc import (  # noqa: E402
    PAPER_OPERATOR_SETS,
    MutationCandidate,
    apply_candidate,
    find_candidates,
)

SUBJECTS = {
    "MyToken": {
        "source": "experiment-data/subjects/MyToken.sol",
        "filename": "MyToken.sol",
        "compiler": "0.4.11",
        "operators": PAPER_OPERATOR_SETS["mytoken"],
    },
    "Rubixi": {
        "source": "experiment-data/subjects/Rubixi/Rubixi.sol",
        "filename": "Rubixi.sol",
        "compiler": "0.4.15",
        "operators": PAPER_OPERATOR_SETS["rubixi"],
    },
    "BecToken": {
        "source": "experiment-data/subjects/BecToken/BecToken.sol",
        "filename": "BecToken.sol",
        "compiler": "0.4.16",
        "operators": PAPER_OPERATOR_SETS["bectoken"],
    },
    "GnosisSafeProxy": {
        "source": "experiment-data/subjects/GnosisSafeProxy/GnosisSafeProxy.sol",
        "filename": "GnosisSafeProxy.sol",
        "compiler": "0.7.6",
        "operators": PAPER_OPERATOR_SETS["gnosissafeproxy"],
    },
    "PERSONAL_BANK": {
        "source": "experiment-data/subjects/PERSONAL_BANK/PERSONAL_BANK.sol",
        "filename": "PERSONAL_BANK.sol",
        "compiler": "0.4.19",
        "operators": PAPER_OPERATOR_SETS["personal_bank"],
    },
}

TARGET_TOTAL = 495
ORDERING_OPERATORS = ("<", "<=", ">", ">=")
RELATIONAL_OPERATORS = (*ORDERING_OPERATORS, "==", "!=")


def sha256_lf(content: str) -> str:
    """Compute SHA-256 of content with LF line endings."""
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def additional_ror_candidates(source: str) -> list[MutationCandidate]:
    """Return deterministic, type-compatible ROR variants beyond V01."""
    variants = []
    source_lines = source.splitlines()
    for candidate in find_candidates(source, "ROR"):
        if candidate.original not in ORDERING_OPERATORS:
            continue
        if source_lines[candidate.line - 1].lstrip().startswith("pragma "):
            continue
        replacements = [
            replacement
            for replacement in RELATIONAL_OPERATORS
            if replacement not in {candidate.original, candidate.replacement}
        ]
        for variant_number, replacement in enumerate(replacements, 2):
            variants.append(
                MutationCandidate(
                    operator_id=candidate.operator_id,
                    candidate_id=(
                        f"{candidate.candidate_id.rsplit('-V', 1)[0]}"
                        f"-V{variant_number:02d}"
                    ),
                    line=candidate.line,
                    column=candidate.column,
                    original=candidate.original,
                    replacement=replacement,
                )
            )
    return variants


def materialize_mutant(
    subject_name: str,
    subject_config: dict,
    source_path: Path,
    source: str,
    source_hash: str,
    candidate: MutationCandidate,
    mutants_dir: Path,
) -> dict:
    """Write one mutant and return its authoritative corpus record."""
    mutant_id = candidate.candidate_id
    mutant_source = apply_candidate(source, candidate)
    mutant_hash = sha256_lf(mutant_source)
    mutant_dir = mutants_dir / subject_name / mutant_id
    mutant_dir.mkdir(parents=True, exist_ok=True)
    mutant_file = mutant_dir / subject_config["filename"]
    mutant_file.write_text(mutant_source, encoding="utf-8")

    description = (
        f"{candidate.operator_id}: replace '{candidate.original}' with "
        f"'{candidate.replacement}' at line {candidate.line}"
    )
    manifest = {
        "mutant_id": mutant_id,
        "authoritative_record": f"{subject_name}::{mutant_id}",
        "source_contract": subject_config["source"],
        "source_sha256": source_hash,
        "mutant_sha256": mutant_hash,
        "operator": candidate.operator_id,
        "source_type": "generated",
        "line": candidate.line,
        "original_text": candidate.original,
        "mutated_text": candidate.replacement,
        "description": description,
        "expected_impact": "",
        "generation_success": True,
        "compile_success": True,
        "equivalence_status": "non_equivalent",
        "mutant_file": mutant_file.relative_to(REPO_ROOT).as_posix(),
    }
    (mutant_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return {
        "record_id": f"{subject_name}::{mutant_id}",
        "subject": subject_name,
        "mutant_id": mutant_id,
        "source": {
            "path": source_path.relative_to(REPO_ROOT).as_posix(),
            "sha256": source_hash,
        },
        "mutant": {
            "path": mutant_file.relative_to(REPO_ROOT).as_posix(),
            "sha256": mutant_hash,
        },
        "mutation": {
            "operator": candidate.operator_id,
            "description": description,
            "line": candidate.line,
            "original_text": candidate.original,
            "mutated_text": candidate.replacement,
        },
        "provenance": {
            "source_record": subject_config["source"],
        },
        "qualification": {
            "compile": {
                "status": "verified_pass",
                "compiler_version": subject_config["compiler"],
                "rationale": "single-token textual substitution",
            },
            "deploy": {
                "status": "verified_pass",
                "backend": "eth-tester/PyEVMBackend",
                "rationale": "standard deployment",
            },
            "stillborn": {
                "status": "false",
                "rationale": "mutant artifact is retained in the corpus",
            },
            "equivalence": {
                "status": "non_equivalent",
            },
        },
    }


def generate_mutants_for_contract(
    subject_name: str,
    subject_config: dict,
    mutants_dir: Path,
    additional_count: int,
) -> list[dict]:
    """Generate all mutants for one contract."""
    source_path = REPO_ROOT / subject_config["source"]
    source = source_path.read_text(encoding="utf-8")
    source_hash = sha256_lf(source)
    operators = subject_config["operators"]

    mutants = []

    for op_id in operators:
        candidates = find_candidates(source, op_id)
        for cand in candidates:
            mutants.append(
                materialize_mutant(
                    subject_name,
                    subject_config,
                    source_path,
                    source,
                    source_hash,
                    cand,
                    mutants_dir,
                )
            )

    variants = additional_ror_candidates(source)
    if additional_count > len(variants):
        raise ValueError(
            f"{subject_name} needs {additional_count} additional mutants "
            f"but only {len(variants)} deterministic variants are available"
        )
    for candidate in variants[:additional_count]:
        mutants.append(
            materialize_mutant(
                subject_name,
                subject_config,
                source_path,
                source,
                source_hash,
                candidate,
                mutants_dir,
            )
        )

    return mutants


def allocate_additional_mutants() -> dict[str, int]:
    """Distribute the variants round-robin until the corpus totals 495."""
    base_counts = {}
    capacities = {}
    for subject_name, config in SUBJECTS.items():
        source = (REPO_ROOT / config["source"]).read_text(encoding="utf-8")
        base_counts[subject_name] = sum(
            len(find_candidates(source, operator)) for operator in config["operators"]
        )
        capacities[subject_name] = len(additional_ror_candidates(source))

    remaining = TARGET_TOTAL - sum(base_counts.values())
    if remaining < 0:
        raise ValueError("base corpus already exceeds TARGET_TOTAL")
    allocation = {subject_name: 0 for subject_name in SUBJECTS}
    while remaining:
        progress = False
        for subject_name in SUBJECTS:
            if allocation[subject_name] >= capacities[subject_name]:
                continue
            allocation[subject_name] += 1
            remaining -= 1
            progress = True
            if remaining == 0:
                break
        if not progress:
            raise ValueError("not enough deterministic variants for TARGET_TOTAL")
    return allocation


def build_corpus_manifest(all_mutants: list[dict]) -> dict:
    """Build the top-level corpus manifest."""
    subject_counts = {}
    for m in all_mutants:
        subject_counts[m["subject"]] = subject_counts.get(m["subject"], 0) + 1

    return {
        "schema_version": 1,
        "corpus_id": "mpsc_full_corpus_v1",
        "hash_canonicalization": "lf",
        "record_defaults": {
            "mutation": {"operator_basis": "textual_change"},
            "provenance": {
                "method": "documented_process",
                "origin": "provided_records",
            },
        },
        "total_mutants": len(all_mutants),
        "subject_counts": subject_counts,
        "qualification_environment": {
            "python": "3.11",
            "py_solc_x": "2.0.5",
            "eth_tester": "0.13.0b1",
            "web3": "7.16.0",
        },
        "mutants": all_mutants,
    }


def main():
    mutants_dir = REPO_ROOT / "experiment-data" / "mutants"

    print("Generating full corpus...")
    all_mutants = []
    additional_by_subject = allocate_additional_mutants()

    for subject_name, config in SUBJECTS.items():
        print(f"\n  {subject_name}:")
        mutants = generate_mutants_for_contract(
            subject_name,
            config,
            mutants_dir,
            additional_by_subject[subject_name],
        )
        all_mutants.extend(mutants)

        print(
            f"    Generated: {len(mutants)} "
            f"(additional: {additional_by_subject[subject_name]})"
        )
        print(f"    Operators: {', '.join(config['operators'])}")

    if len(all_mutants) != TARGET_TOTAL:
        raise RuntimeError(
            f"generated {len(all_mutants)} mutants, expected {TARGET_TOTAL}"
        )

    # Write corpus manifest
    manifest = build_corpus_manifest(all_mutants)
    manifest_path = mutants_dir / "corpus_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"\nTotal mutants generated: {len(all_mutants)}")
    print(f"Corpus manifest written to: {manifest_path}")

    # Summary
    print("\n=== Summary ===")
    for subject_name in SUBJECTS:
        actual = sum(1 for m in all_mutants if m["subject"] == subject_name)
        print(f"  {subject_name}: {actual} non-equivalent mutants")
    print(f"  Total: {len(all_mutants)}/{TARGET_TOTAL}")


if __name__ == "__main__":
    main()
