import json

import pytest
from mpsc.experiments.canonical_scores import (
    derive_canonical_mutation_scores,
)


def test_scores_are_derived_from_all_raw_canonical_runs(tmp_path):
    result = derive_canonical_mutation_scores(tmp_path)

    assert result["raw_runs_consumed"] == 120
    assert result["kill_vectors"] == {
        "MR6.1": {"MUT-01": 0, "MUT-07": 0, "MUT-08": 1},
        "MR6.4": {"MUT-01": 0, "MUT-07": 0, "MUT-08": 0},
        "MR6.6": {"MUT-01": 0, "MUT-07": 0, "MUT-08": 1},
    }
    assert result["mutation_scores"] == {
        "MR6.1": pytest.approx(1 / 3),
        "MR6.4": 0.0,
        "MR6.6": pytest.approx(1 / 3),
    }
    assert all(cell["TCE"] == 10 for cell in result["cells"])
    saved = json.loads((tmp_path / "kill_vectors.json").read_text(encoding="utf-8"))
    assert saved["cells"] == result["cells"]
