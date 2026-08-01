import csv
from collections import Counter
from pathlib import Path

import yaml

FINDINGS = Path("experiment-data/processed/vulnerability_findings.csv")
TIMING = Path("experiment-data/processed/method_time_comparison.csv")


def _rows(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_supplied_finding_matrix_has_complete_aggregate_shape():
    rows = _rows(FINDINGS)

    assert len(rows) == 100
    assert len({row["contract"] for row in rows}) == 5
    assert len({row["vulnerability_type"] for row in rows}) == 5
    assert Counter(row["method"] for row in rows) == Counter(
        {"MPSC": 25, "VDMBSCMT": 25, "Solhint": 25, "Slither": 25}
    )
    totals = {
        method: sum(
            int(row["confirmed_count"]) for row in rows if row["method"] == method
        )
        for method in ("MPSC", "VDMBSCMT", "Solhint", "Slither")
    }
    assert totals == {"MPSC": 9, "VDMBSCMT": 2, "Solhint": 4, "Slither": 5}


def test_supplied_time_summary_and_source_hashes_are_frozen():
    rows = _rows(TIMING)
    assert len(rows) == 4
    assert {row["method"] for row in rows} == {
        "MPSC",
        "VDMBSCMT",
        "Solhint",
        "Slither",
    }
    assert all(float(row["total_time_seconds"]) > 0 for row in rows)
    assert len({row["source_sha256"] for row in rows}) == 1


def test_no_tool_is_presented_as_an_exact_supplied_environment():
    rows = _rows(FINDINGS)
    assert {row["method"] for row in rows} == {
        "MPSC",
        "VDMBSCMT",
        "Solhint",
        "Slither",
    }
    assert all(row["source_role"] == "supplied_office" for row in rows)


def test_control_run_template_is_disabled_until_provenance_is_filled():
    template = yaml.safe_load(
        Path("code/configs/comparison_tools/control_run_template.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert template["claim_class"] == "control"
    assert "paper_validation" not in template
    assert len(template["subjects"]) == 5
    assert all(not row["enabled"] for row in template["tools"].values())
    assert all(not row["command"] for row in template["tools"].values())
    assert "raw_findings/" in template["output_requirements"]
    assert "manual_confirmation.jsonl" in template["output_requirements"]
