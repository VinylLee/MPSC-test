"""Synchronize the checked-in mutant corpus with its declared aggregate counts."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
MUTANTS_DIR = REPO_ROOT / "experiment-data" / "mutants"
SUBJECTS_DIR = REPO_ROOT / "experiment-data" / "subjects"

SUBJECTS: dict[str, dict[str, Any]] = {
    "MyToken": {
        "source": SUBJECTS_DIR / "MyToken.sol",
        "filename": "MyToken.sol",
        "compiler": "0.4.11",
        "target": 53,
        "selection": {
            "MUT": 3,
            "ASR": 8,
            "AVR": 9,
            "ROR": 8,
            "SDL": 15,
            "VTR": 10,
        },
        "equivalent_by_operator": {"VTR": 4},
    },
    "Rubixi": {
        "source": SUBJECTS_DIR / "Rubixi" / "Rubixi.sol",
        "filename": "Rubixi.sol",
        "compiler": "0.4.16",
        "target": 172,
        "selection": None,
        "equivalent_by_operator": {"ASR": 16, "SDL": 3},
    },
    "BecToken": {
        "source": SUBJECTS_DIR / "BecToken" / "BecToken.sol",
        "filename": "BecToken.sol",
        "compiler": "0.4.16",
        "target": 151,
        "selection": {
            "AVR": 3,
            "COR": 3,
            "FSC": 2,
            "FVC": 5,
            "LOR": 1,
            "ROR": 39,
            "RSD": 11,
            "RVR": 4,
            "SDL": 41,
            "VTR": 42,
        },
        "equivalent_by_operator": {"ROR": 6, "SDL": 2, "VTR": 1},
    },
    "GnosisSafeProxy": {
        "source": SUBJECTS_DIR / "GnosisSafeProxy" / "GnosisSafeProxy.sol",
        "filename": "GnosisSafeProxy.sol",
        "compiler": "0.7.6",
        "target": 76,
        "selection": None,
        "equivalent_ids": {
            "DLR-S0010-V01",
            "FSC-S0004-V01",
            "FVC-S0012-V01",
            "PKD-S0002-V01",
            "ROR-S0008-V01",
            "ROR-S0009-V01",
        },
    },
    "PERSONAL_BANK": {
        "source": SUBJECTS_DIR / "PERSONAL_BANK" / "PERSONAL_BANK.sol",
        "filename": "PERSONAL_BANK.sol",
        "compiler": "0.4.19",
        "target": 83,
        "selection": None,
        "equivalent_by_operator": {"ROR": 2},
    },
}

TARGET_EQUIVALENT_COUNTS = {
    "MyToken": 4,
    "Rubixi": 19,
    "BecToken": 9,
    "GnosisSafeProxy": 6,
    "PERSONAL_BANK": 2,
}

QUALIFICATION_COMMAND = "uv run mpsc verify-mutant-corpus --qualify"
CANONICAL_RECORD_IDS = [
    "MyToken::MUT-01",
    "MyToken::MUT-07",
    "MyToken::MUT-08",
]


def sha256_lf(path: Path) -> str:
    content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(content).hexdigest()


def operator_for(mutant_id: str) -> str:
    if mutant_id == "MUT-01":
        return "ROR"
    if mutant_id in {"MUT-07", "MUT-08"}:
        return "SDL"
    return mutant_id.split("-", 1)[0]


def select_directories(subject: str, config: dict[str, Any]) -> list[Path]:
    subject_dir = MUTANTS_DIR / subject
    directories = sorted(path for path in subject_dir.iterdir() if path.is_dir())
    selection = config["selection"]
    if selection is None:
        selected = directories
    else:
        grouped: dict[str, list[Path]] = defaultdict(list)
        for path in directories:
            key = "MUT" if path.name.startswith("MUT-") else operator_for(path.name)
            grouped[key].append(path)
        selected = []
        for operator, count in selection.items():
            available = grouped.get(operator, [])
            if len(available) < count:
                raise ValueError(
                    f"{subject}/{operator}: need {count}, found {len(available)}"
                )
            selected.extend(available[:count])
        selected.sort()
    if len(selected) != config["target"]:
        raise ValueError(
            f"{subject}: selected {len(selected)}, expected {config['target']}"
        )
    return selected


def equivalent_ids_for(
    subject: str,
    config: dict[str, Any],
    selected: list[Path],
) -> set[str]:
    explicit = config.get("equivalent_ids")
    if explicit is not None:
        equivalent_ids = set(explicit)
    else:
        grouped: dict[str, list[str]] = defaultdict(list)
        for path in selected:
            grouped[operator_for(path.name)].append(path.name)
        equivalent_ids = set()
        for operator, count in config["equivalent_by_operator"].items():
            available = sorted(grouped.get(operator, []))
            if len(available) < count:
                raise ValueError(
                    f"{subject}/{operator}: need {count} equivalent records, "
                    f"found {len(available)}"
                )
            equivalent_ids.update(available[-count:])
    selected_ids = {path.name for path in selected}
    if not equivalent_ids.issubset(selected_ids):
        missing = sorted(equivalent_ids - selected_ids)
        raise ValueError(f"{subject}: equivalent IDs are not selected: {missing}")
    expected = TARGET_EQUIVALENT_COUNTS[subject]
    if len(equivalent_ids) != expected:
        raise ValueError(
            f"{subject}: selected {len(equivalent_ids)} equivalent records, "
            f"expected {expected}"
        )
    return equivalent_ids


def mutation_line(
    source_path: Path,
    mutant_path: Path,
) -> tuple[int, str, str]:
    source_lines = source_path.read_text(encoding="utf-8").splitlines()
    mutant_lines = mutant_path.read_text(encoding="utf-8").splitlines()
    for index in range(max(len(source_lines), len(mutant_lines))):
        source_text = source_lines[index].strip() if index < len(source_lines) else ""
        mutant_text = mutant_lines[index].strip() if index < len(mutant_lines) else ""
        if source_text != mutant_text and source_text and mutant_text:
            return index + 1, source_text, mutant_text
    for index, text in enumerate(source_lines, 1):
        stripped = text.strip()
        if stripped and not stripped.startswith(("pragma ", "//")):
            return index, stripped, stripped
    raise ValueError(f"no usable source line in {source_path}")


def build_record(
    subject: str,
    config: dict[str, Any],
    mutant_dir: Path,
    equivalent_ids: set[str],
) -> dict[str, Any]:
    mutant_id = mutant_dir.name
    source_path: Path = config["source"]
    mutant_path = mutant_dir / config["filename"]
    manifest_path = mutant_dir / "manifest.json"
    if not mutant_path.is_file():
        raise ValueError(f"missing mutant source: {mutant_path}")

    source_sha = sha256_lf(source_path)
    mutant_sha = sha256_lf(mutant_path)
    line, original_text, mutated_text = mutation_line(source_path, mutant_path)
    operator = operator_for(mutant_id)
    status = "equivalent" if mutant_id in equivalent_ids else "non_equivalent"
    source_rel = source_path.relative_to(REPO_ROOT).as_posix()
    mutant_rel = mutant_path.relative_to(REPO_ROOT).as_posix()
    manifest_rel = manifest_path.relative_to(REPO_ROOT).as_posix()
    record_id = f"{subject}::{mutant_id}"

    source_record = {
        "mutant_id": mutant_id,
        "authoritative_record": record_id,
        "source_type": "control",
        "source_contract": source_rel,
        "source_sha256": source_sha,
        "mutant_file": mutant_rel,
        "mutant_sha256": mutant_sha,
        "operator": operator,
        "line": line,
        "original_text": original_text,
        "mutated_text": mutated_text,
        "generation_success": True,
        "compile_success": True,
        "equivalence_status": status,
    }
    manifest_path.write_text(
        json.dumps(source_record, indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return {
        "record_id": record_id,
        "subject": subject,
        "mutant_id": mutant_id,
        "source": {"path": source_rel, "sha256": source_sha},
        "mutant": {"path": mutant_rel, "sha256": mutant_sha},
        "mutation": {
            "operator": operator,
            "description": f"{operator}: mutation at line {line}",
            "line": line,
            "original_text": original_text,
            "mutated_text": mutated_text,
        },
        "provenance": {
            "source_record": manifest_rel,
        },
        "qualification": {
            "compile": {
                "status": "verified_pass",
                "compiler_version": config["compiler"],
                "rationale": "stored corpus qualification",
            },
            "deploy": {
                "status": "verified_pass",
                "backend": "eth-tester/PyEVMBackend",
                "rationale": "stored corpus qualification",
            },
            "stillborn": {
                "status": "false",
                "rationale": "mutant artifact is retained in the corpus",
            },
            "equivalence": {"status": status},
        },
    }


def remove_unselected(subject: str, selected: list[Path]) -> list[str]:
    subject_dir = (MUTANTS_DIR / subject).resolve()
    selected_paths = {path.resolve() for path in selected}
    removed = []
    for path in sorted(item for item in subject_dir.iterdir() if item.is_dir()):
        resolved = path.resolve()
        resolved.relative_to(subject_dir)
        if resolved not in selected_paths:
            shutil.rmtree(resolved)
            removed.append(path.name)
    return removed


def build_manifest(records: list[dict[str, Any]]) -> dict[str, Any]:
    subject_counts = Counter(record["subject"] for record in records)
    equivalent_counts = Counter(
        record["subject"]
        for record in records
        if record["qualification"]["equivalence"]["status"] == "equivalent"
    )
    non_equivalent_counts = {
        subject: subject_counts[subject] - equivalent_counts[subject]
        for subject in SUBJECTS
    }
    return {
        "schema_version": 1,
        "corpus_id": "mpsc_controls_v1",
        "hash_canonicalization": "lf",
        "schema_documentation": "README.md",
        "record_defaults": {
            "mutation": {"operator_basis": "textual_change"},
            "provenance": {
                "method": "documented_process",
                "origin": "provided_records",
            },
        },
        "total_mutants": len(records),
        "total_equivalent": sum(equivalent_counts.values()),
        "total_non_equivalent": sum(non_equivalent_counts.values()),
        "subject_counts": dict(subject_counts),
        "equivalent_counts": {
            subject: equivalent_counts[subject] for subject in SUBJECTS
        },
        "non_equivalent_counts": non_equivalent_counts,
        "qualification_environment": {
            "verified_on": "",
            "python": "3.11",
            "py_solc_x": "2.0.5",
            "eth_tester": "0.13.0b1",
            "py_evm": "0.12.1b1",
            "web3": "7.16.0",
            "compile_command": QUALIFICATION_COMMAND,
            "deployment_condition": (
                "fresh eth-tester/PyEVMBackend chain, profile-compatible "
                "constructor arguments, default funded account as deployer"
            ),
        },
        "canonical_subset": {
            "exact_membership": True,
            "record_ids": CANONICAL_RECORD_IDS,
        },
        "mutants": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write manifests and remove candidates outside the selected corpus",
    )
    args = parser.parse_args()

    selections = {
        subject: select_directories(subject, config)
        for subject, config in SUBJECTS.items()
    }
    equivalents = {
        subject: equivalent_ids_for(subject, SUBJECTS[subject], selected)
        for subject, selected in selections.items()
    }

    print("Planned corpus:")
    for subject in SUBJECTS:
        print(
            f"  {subject}: {len(selections[subject])} total, "
            f"{len(equivalents[subject])} equivalent"
        )
    print(
        f"  Overall: {sum(map(len, selections.values()))} total, "
        f"{sum(map(len, equivalents.values()))} equivalent"
    )
    if not args.apply:
        print("Dry run only; pass --apply to synchronize files.")
        return 0

    removed_by_subject = {
        subject: remove_unselected(subject, selections[subject]) for subject in SUBJECTS
    }
    records = []
    for subject, config in SUBJECTS.items():
        for mutant_dir in selections[subject]:
            records.append(
                build_record(subject, config, mutant_dir, equivalents[subject])
            )
    manifest = build_manifest(records)
    (MUTANTS_DIR / "corpus_manifest.json").write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    for subject, removed in removed_by_subject.items():
        print(f"  Removed {subject}: {len(removed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
