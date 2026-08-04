"""Render the extended comparison figures that include ItyFuzz."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

PROCESSED_DIR = Path("experiment-data/processed")
COLORS = ["#d94841", "#9b6acd", "#2f77b5", "#41a36f", "#f4a261"]


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate_ityfuzz_figures(
    *,
    input_dir: str | Path = PROCESSED_DIR,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Render deterministic extended-comparison figures from published CSVs."""

    source = Path(input_dir)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    vulnerability_csv = source / "ityfuzz" / "ityfuzz_vulnerability_comparison.csv"
    time_csv = source / "ityfuzz" / "ityfuzz_method_time.csv"

    vulnerability_figure = output / "ityfuzz_vulnerability_comparison.pdf"
    time_figure = output / "ityfuzz_time_comparison.pdf"
    _render_vulnerability_comparison(vulnerability_csv, vulnerability_figure)
    _render_time_comparison(time_csv, time_figure)

    figures = [
        {
            "path": vulnerability_figure.as_posix(),
            "source_csv": vulnerability_csv.as_posix(),
            "source_sha256": _sha256(vulnerability_csv),
        },
        {
            "path": time_figure.as_posix(),
            "source_csv": time_csv.as_posix(),
            "source_sha256": _sha256(time_csv),
        },
    ]
    manifest = {
        "schema_version": 1,
        "campaign_id": "mpsc-ityfuzz-comparison-v1",
        "evidence_class": "computed",
        "figure_count": len(figures),
        "figures": figures,
    }
    (output / "figures_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _render_vulnerability_comparison(source: Path, destination: Path) -> None:
    rows = _rows(source)
    vulnerabilities = list(dict.fromkeys(row["vulnerability_type"] for row in rows))
    methods = list(dict.fromkeys(row["method"] for row in rows))
    labels = {
        "access_control": "Access\ncontrol",
        "short_address_attack": "Short\naddress",
        "compiler_version": "Compiler\nversion",
        "integer_overflow": "Overflow /\nunderflow",
        "reentrancy": "Reentrancy",
    }
    x = np.arange(len(vulnerabilities))
    width = 0.15
    figure, axis = plt.subplots(figsize=(10.5, 5.8))
    for index, method in enumerate(methods):
        values = [
            int(
                next(
                    row["detected_count"]
                    for row in rows
                    if row["vulnerability_type"] == vulnerability
                    and row["method"] == method
                )
            )
            for vulnerability in vulnerabilities
        ]
        offset = (index - (len(methods) - 1) / 2) * width
        bars = axis.bar(x + offset, values, width, label=method, color=COLORS[index])
        axis.bar_label(bars, padding=2, fontsize=8)
    axis.set_ylabel("Detected vulnerabilities")
    axis.set_xticks(x, [labels[item] for item in vulnerabilities])
    axis.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    axis.grid(axis="y", alpha=0.2)
    axis.legend(frameon=False)
    figure.tight_layout()
    figure.savefig(destination, bbox_inches="tight")
    plt.close(figure)


def _render_time_comparison(source: Path, destination: Path) -> None:
    rows = _rows(source)
    methods = [row["method"] for row in rows]
    times = [float(row["total_time_seconds"]) for row in rows]
    findings = [int(row["detected_vulnerabilities"]) for row in rows]
    x = np.arange(len(methods))

    figure, finding_axis = plt.subplots(figsize=(9, 5.8))
    bars = finding_axis.bar(x, findings, width=0.58, color=COLORS[0])
    finding_axis.bar_label(bars, padding=3, fontsize=9)
    finding_axis.set_ylabel("Detected vulnerabilities")
    finding_axis.set_xticks(x, methods)
    finding_axis.set_ylim(0, max(findings) * 1.12)
    finding_axis.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    finding_axis.grid(axis="y", alpha=0.2)

    time_axis = finding_axis.twinx()
    time_axis.plot(x, times, color=COLORS[2], marker="o", linewidth=2)
    time_axis.set_ylabel("Time overhead (seconds)")
    time_axis.set_ylim(0, max(times) * 1.12)
    for index, value in enumerate(times):
        time_axis.annotate(
            f"{value:.0f} s",
            (x[index], value),
            xytext=(34 if index == 0 else 0, 8),
            textcoords="offset points",
            ha="center",
            fontsize=8,
        )
    figure.tight_layout()
    figure.savefig(destination, bbox_inches="tight")
    plt.close(figure)
