import json

import matplotlib.image as mpimg
from mpsc.reporting import (
    generate_figures,
)


def test_generates_all_figures_from_processed_data(tmp_path):
    figures = tmp_path / "figures"

    manifest = generate_figures(
        input_dir="experiment-data/processed",
        output_dir=figures,
    )

    assert manifest["figure_count"] == 7
    assert {item["path"].split("/")[-1] for item in manifest["figures"]} == {
        "mr_counts.png",
        "method_comparison.png",
        "vulnerability_comparison.png",
        "optimization.png",
        "method_time.png",
        "appendix_mr_sensitivity.png",
        "appendix_mrd_distribution.png",
    }
    for item in manifest["figures"]:
        image = mpimg.imread(item["path"])
        assert image.shape[0] >= 700
        assert image.shape[1] >= 1000
        assert item["size_bytes"] > 20_000
        assert item["source_csvs"]

    saved = json.loads((figures / "figures_manifest.json").read_text("utf-8"))
    assert saved == manifest
