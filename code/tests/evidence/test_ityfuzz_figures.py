import csv
import json

from mpsc.reporting.ityfuzz import generate_ityfuzz_figures


def test_extended_comparison_data_and_figures_are_deterministic(tmp_path):
    with open(
        "experiment-data/processed/ityfuzz/ityfuzz_vulnerability_comparison.csv",
        encoding="utf-8",
        newline="",
    ) as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 25
    assert {row["method"] for row in rows} == {
        "MPSC",
        "VDMBSCMT",
        "Solhint",
        "Slither",
        "ItyFuzz",
    }
    ityfuzz_total = sum(
        int(row["detected_count"]) for row in rows if row["method"] == "ItyFuzz"
    )
    assert ityfuzz_total == 8

    output = tmp_path / "figures"
    manifest = generate_ityfuzz_figures(output_dir=output)
    assert manifest["figure_count"] == 2
    assert (output / "ityfuzz_vulnerability_comparison.pdf").is_file()
    assert (output / "ityfuzz_time_comparison.pdf").is_file()
    saved = json.loads((output / "figures_manifest.json").read_text("utf-8"))
    assert saved["campaign_id"] == "mpsc-ityfuzz-comparison-v1"
