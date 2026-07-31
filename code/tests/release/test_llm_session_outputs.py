from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SESSION_ROOT = Path("experiment-data/llm/gpt5_session")
EXPECTED_SUBJECTS = {
    "mytoken",
    "rubixi",
    "bectoken",
    "gnosissafeproxy",
    "personal_bank",
}


def test_gpt5_outputs_are_complete_and_source_bound():
    completed = subprocess.run(
        [sys.executable, "code/scripts/verify_llm_session_outputs.py"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result == {
        "status": "pass",
        "output_count": 5,
        "candidate_count": 69,
        "errors": [],
    }


def test_gpt5_response_records_use_the_current_top_level_schema():
    response_files = sorted((SESSION_ROOT / "subjects").glob("*/response.json"))

    assert {path.parent.name for path in response_files} == EXPECTED_SUBJECTS
    for path in response_files:
        response = json.loads(path.read_text("utf-8"))
        assert response["schema_version"] == 1
        assert response["run_id"] == "gpt5"
        assert response["subject_id"] == path.parent.name
        assert "status" not in response
        assert "independent_review_status" not in response
        assert Path(response["request"]["source_path"]).is_file()
