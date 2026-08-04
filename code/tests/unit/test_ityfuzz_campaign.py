from pathlib import Path

from mpsc.comparison.ityfuzz import analyze_detection_time, validate_campaign


def test_integrated_ityfuzz_campaign_is_complete():
    result = validate_campaign()

    assert result["status"] == "pass", result["errors"]
    assert result["subject_count"] == 11
    assert result["recorded_run_count"] == 4
    assert result["recorded_run_file_count"] == 496
    assert result["ityfuzz_commit"] == "35b7f08962fdd0c2e02df7ef8a43164913d514d9"


def test_detection_time_analyzer_handles_recorded_bectoken_corpus():
    result = analyze_detection_time(
        Path("experiment-data/results/canonical/ityfuzz/runs/bectoken")
    )

    assert result["status"] in {"pass", "not_found"}
    assert result["corpus_file_count"] > 0
