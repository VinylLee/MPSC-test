import hashlib
import json
from collections import Counter
from pathlib import Path

MANIFEST = Path("experiment-data/mutants/corpus_manifest.json")
EXPECTED_SUBJECT_COUNTS = {
    "MyToken": 53,
    "Rubixi": 172,
    "BecToken": 151,
    "GnosisSafeProxy": 76,
    "PERSONAL_BANK": 83,
}
EXPECTED_EQUIVALENT_COUNTS = {
    "MyToken": 4,
    "Rubixi": 19,
    "BecToken": 9,
    "GnosisSafeProxy": 6,
    "PERSONAL_BANK": 2,
}


def _sha256_lf(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def test_full_corpus_has_495_non_equivalent_mutants():
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    records = payload["mutants"]

    assert payload["total_mutants"] == len(records) == 535
    assert payload["total_equivalent"] == 40
    assert payload["total_non_equivalent"] == 495
    assert payload["subject_counts"] == EXPECTED_SUBJECT_COUNTS
    assert payload["equivalent_counts"] == EXPECTED_EQUIVALENT_COUNTS
    assert payload["non_equivalent_counts"] == {
        subject: EXPECTED_SUBJECT_COUNTS[subject] - equivalent
        for subject, equivalent in EXPECTED_EQUIVALENT_COUNTS.items()
    }
    assert Counter(record["subject"] for record in records) == Counter(
        EXPECTED_SUBJECT_COUNTS
    )
    assert {record["qualification"]["equivalence"]["status"] for record in records} == {
        "equivalent",
        "non_equivalent",
    }
    assert len({record["record_id"] for record in records}) == 535
    assert len({record["mutant"]["path"] for record in records}) == 535


def test_full_corpus_files_and_hashes_match_the_manifest():
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))

    for record in payload["mutants"]:
        mutant_path = Path(record["mutant"]["path"])
        assert mutant_path.is_file(), record["record_id"]
        assert _sha256_lf(mutant_path) == record["mutant"]["sha256"]

        per_file_manifest = mutant_path.with_name("manifest.json")
        per_file = json.loads(per_file_manifest.read_text(encoding="utf-8"))
        assert per_file["equivalence_status"] in ("non_equivalent", "equivalent")


def test_corpus_schema_fields_are_consistent():
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert "evidence_class" not in payload
    assert "claim_boundary" not in payload
    assert payload["record_defaults"] == {
        "mutation": {"operator_basis": "textual_change"},
        "provenance": {
            "method": "documented_process",
            "origin": "provided_records",
        },
    }
    assert "evidence_class" not in payload["canonical_subset"]
    qualification_counts = Counter()
    for record in payload["mutants"]:
        assert "evidence_class" not in record
        assert "operator_basis" not in record["mutation"]
        assert "method" not in record["provenance"]
        assert "origin" not in record["provenance"]
        assert record["provenance"]["source_record"]
        qualification = record["qualification"]
        assert "rationale" not in qualification["equivalence"]
        statuses = (
            qualification["compile"]["status"],
            qualification["deploy"]["status"],
        )
        qualification_counts[statuses] += 1
        assert qualification["stillborn"] == {
            "status": "false",
            "rationale": "mutant artifact is retained in the corpus",
        }
    assert qualification_counts == Counter(
        {
            ("verified_pass", "verified_pass"): 441,
            ("verified_fail", "not_verified"): 91,
            ("verified_pass", "verified_fail"): 3,
        }
    )
