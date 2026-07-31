"""Arithmetic and provenance checks for the mutant count chain."""

import csv
import json
from collections import Counter
from pathlib import Path

EVIDENCE = Path("experiment-data/mutants/corpus_manifest.json")


def _load_evidence():
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def test_operator_rows_recompute_every_contract_and_total():
    evidence = _load_evidence()
    records = evidence["mutants"]
    generated = Counter(row["subject"] for row in records)
    equivalent = Counter(
        row["subject"]
        for row in records
        if row["qualification"]["equivalence"]["status"] == "equivalent"
    )

    assert dict(generated) == evidence["subject_counts"]
    assert dict(equivalent) == evidence["equivalent_counts"]
    assert evidence["total_mutants"] == 535
    assert evidence["total_equivalent"] == 40
    assert evidence["total_non_equivalent"] == 495


def test_normalized_csv_matches_evidence_chain():
    evidence = _load_evidence()
    with Path("experiment-data/processed/mutant_counts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    normalized = {
        row["contract"]: (
            int(row["generated_mutants"]),
            int(row["equivalent_mutants"]),
            int(row["valid_mutants"]),
        )
        for row in rows
    }
    expected = {
        contract: (
            evidence["subject_counts"][contract],
            evidence["equivalent_counts"][contract],
            evidence["non_equivalent_counts"][contract],
        )
        for contract in evidence["subject_counts"]
    }
    assert normalized == expected


def test_source_hashes_and_identity_boundary_are_frozen():
    rows = []
    with Path("experiment-data/processed/mutant_counts.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    manifest = json.loads(
        Path("experiment-data/processed/provenance_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    audited_hashes = {row["path"]: row["sha256"] for row in manifest["files"]}
    for row in rows:
        assert audited_hashes[row["source_path"]] == row["source_sha256"]


def test_operator_list_discrepancies_are_not_silenced():
    evidence = _load_evidence()
    records = evidence["mutants"]
    assert len({row["record_id"] for row in records}) == len(records)
    assert all(row["mutation"]["operator"] for row in records)
    assert set(evidence["subject_counts"]) == {
        "MyToken",
        "Rubixi",
        "BecToken",
        "GnosisSafeProxy",
        "PERSONAL_BANK",
    }
