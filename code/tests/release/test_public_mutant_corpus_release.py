import json
from pathlib import Path

import yaml
from click.testing import CliRunner
from mpsc.cli import main
from mpsc.mutation.corpus import validate_public_corpus


def test_reviewer_facing_corpus_is_complete():
    result = validate_public_corpus()

    assert result["status"] == "pass", result["errors"]
    assert result["declared_total"] == 535
    assert result["equivalent_counts"] == {
        "MyToken": 4,
        "Rubixi": 19,
        "BecToken": 9,
        "GnosisSafeProxy": 6,
        "PERSONAL_BANK": 2,
    }
    assert result["canonical_record_ids"] == [
        "MyToken::MUT-01",
        "MyToken::MUT-07",
        "MyToken::MUT-08",
    ]
    canonical = yaml.safe_load(
        Path("code/configs/experiments/mytoken_canonical_mutants.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert {
        f"MyToken::{record['mutant_id']}" for record in canonical["mutants"]
    } == set(result["canonical_record_ids"])


def test_mutant_source_records_have_minimal_identity_metadata():
    for path in Path("experiment-data/mutants").glob("*/*/manifest.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        assert "evidence_class" not in record
        assert "equivalence_rationale" not in record
        assert record["source_type"] == "control"


def test_public_mutant_inventory_is_read_only_verifiable():
    result = validate_public_corpus()

    assert result["status"] == "pass", result["errors"]
    assert result["disk_total"] == 535


def test_cli_reports_tamper_with_nonzero_exit(tmp_path):
    manifest = json.loads(
        Path("experiment-data/mutants/corpus_manifest.json").read_text(encoding="utf-8")
    )
    manifest["total_mutants"] = 495
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(manifest), encoding="utf-8")

    result = CliRunner().invoke(
        main,
        ["verify-mutant-corpus", "--manifest", str(changed)],
    )

    assert result.exit_code == 1
    assert '"status": "fail"' in result.output
    assert "total_mutants" in result.output
