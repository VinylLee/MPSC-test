from pathlib import Path

import pytest
import yaml
from mpsc.mutation.corpus import (
    canonical_source_sha256,
    validate_frozen_corpus,
    write_corpus_validation,
)


def test_canonical_mutant_corpus_is_frozen_and_eligible(tmp_path):
    output = tmp_path / "corpus.json"
    report = write_corpus_validation(output)

    assert report["valid"] is True
    assert report["mutant_count"] == 3
    assert report["eligible_count"] == 3
    assert report["ineligible_count"] == 0
    assert [item["mutant_id"] for item in report["mutants"]] == [
        "MUT-01",
        "MUT-07",
        "MUT-08",
    ]
    assert {item["origin"] for item in report["mutants"]} == {
        "local_engineering_generator"
    }
    assert output.is_file()


def test_hashes_match_canonical_content():
    report = validate_frozen_corpus()

    assert report["hash_mismatch_count"] == 0
    assert all(
        item["frozen_hash_matches"] and item["hash_matches"]
        for item in report["mutants"]
    )


def test_canonical_source_hash_is_portable_across_line_endings(tmp_path):
    lf = tmp_path / "lf.sol"
    crlf = tmp_path / "crlf.sol"
    lf.write_bytes(b"pragma solidity 0.4.11;\ncontract C {}\n")
    crlf.write_bytes(b"pragma solidity 0.4.11;\r\ncontract C {}\r\n")

    assert canonical_source_sha256(lf) == canonical_source_sha256(crlf)


def test_changed_mutant_fails_frozen_hash_validation(tmp_path):
    config = yaml.safe_load(
        Path("code/configs/experiments/mytoken_canonical_mutants.yaml").read_text(
            encoding="utf-8"
        )
    )
    changed = tmp_path / "changed.sol"
    changed.write_text("contract Changed {}", encoding="utf-8")
    config["mutants"][0]["path"] = changed.as_posix()
    config_path = tmp_path / "corpus.yaml"
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_frozen_corpus(config_path)

    assert report["valid"] is False
    assert report["mutants"][0]["eligibility_status"] == "ineligible"


def test_duplicate_mutant_ids_are_rejected(tmp_path):
    config = yaml.safe_load(
        Path("code/configs/experiments/mytoken_canonical_mutants.yaml").read_text(
            encoding="utf-8"
        )
    )
    config["mutants"][1]["mutant_id"] = config["mutants"][0]["mutant_id"]
    config_path = tmp_path / "duplicate.yaml"
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate mutant ID"):
        validate_frozen_corpus(config_path)


def test_unknown_provenance_class_is_ignored(tmp_path):
    config = yaml.safe_load(
        Path("code/configs/experiments/mytoken_canonical_mutants.yaml").read_text(
            encoding="utf-8"
        )
    )
    config["mutants"][0]["provenance_class"] = "musc_maybe"
    config_path = tmp_path / "unknown.yaml"
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_frozen_corpus(config_path)

    assert report["valid"] is True


def test_claim_field_is_ignored(tmp_path):
    config = yaml.safe_load(
        Path("code/configs/experiments/mytoken_canonical_mutants.yaml").read_text(
            encoding="utf-8"
        )
    )
    config["mutants"][0]["claim"] = "independent_mutation_run"
    config_path = tmp_path / "claim.yaml"
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_frozen_corpus(config_path)

    assert report["valid"] is True
