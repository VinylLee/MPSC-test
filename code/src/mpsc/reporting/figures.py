"""Render result figures from processed CSV data."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

PROCESSED_DIR = Path("experiment-data/processed")
FIGURE_DIR = Path("experiment-data/results/reports/figures")
_COLORS = ["#35618f", "#d77a33", "#4b8f58", "#9a5fb4"]


def generate_figures(
    *,
    input_dir: str | Path = PROCESSED_DIR,
    output_dir: str | Path = FIGURE_DIR,
) -> dict[str, Any]:
    """Render all result figures from processed CSVs, never from hand-entered data."""

    source = Path(input_dir)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    figure_specs = [
        (
            "mr_counts.png",
            _figure_mr_counts,
            ["subject_mr_counts.csv"],
        ),
        (
            "method_comparison.png",
            _figure_method_comparison,
            ["mr_method_comparison.csv"],
        ),
        (
            "vulnerability_comparison.png",
            _figure_vulnerability_comparison,
            ["computed/vulnerability_totals.csv"],
        ),
        (
            "optimization.png",
            _figure_optimization,
            ["computed/optimization.csv"],
        ),
        (
            "method_time.png",
            _figure_method_time,
            ["method_time_comparison.csv"],
        ),
        (
            "appendix_mr_sensitivity.png",
            _figure_mr_sensitivity,
            ["mytoken_mr_sensitivity.csv"],
        ),
        (
            "appendix_mrd_distribution.png",
            _figure_mrd_distribution,
            ["mytoken_mrd_pairs.csv"],
        ),
    ]

    figures = []
    for filename, renderer, inputs in figure_specs:
        destination = output / filename
        renderer(source, destination)
        figures.append(
            {
                "path": destination.as_posix(),
                "source_csvs": [(source / item).as_posix() for item in inputs],
                "size_bytes": destination.stat().st_size,
            }
        )

    manifest = {
        "schema_version": 1,
        "claim_status": "computed",
        "figure_count": len(figures),
        "figures": figures,
    }
    (output / "figures_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _figure_mr_counts(source: Path, destination: Path) -> None:
    rows = _read_csv(source / "subject_mr_counts.csv")
    labels = [row["contract"] for row in rows]
    mutable = [int(row["mutable_parameter_count"]) for row in rows]
    mrs = [int(row["mr_count"]) for row in rows]
    x = np.arange(len(labels))
    width = 0.36

    figure, axis = plt.subplots(figsize=(10, 5.6))
    _bars(axis, x - width / 2, mutable, width, "Mutable parameters", _COLORS[0])
    _bars(axis, x + width / 2, mrs, width, "Constructed MRs", _COLORS[1])
    axis.set_title("Subject mutable-parameter and MR counts")
    axis.set_ylabel("Count")
    _finish_grouped_axis(axis, x, labels)
    _save(figure, destination)


def _figure_method_comparison(source: Path, destination: Path) -> None:
    rows = _read_csv(source / "mr_method_comparison.csv")
    contracts = list(dict.fromkeys(row["contract"] for row in rows))
    methods = list(dict.fromkeys(row["method"] for row in rows))
    labels = {
        "manual": "Manual",
        "vulnerability_oriented": "Vulnerability-oriented",
        "object_oriented": "Object-oriented",
        "mpsc": "MPSC",
    }
    x = np.arange(len(contracts))
    width = 0.19

    figure, axis = plt.subplots(figsize=(11, 5.8))
    for index, method in enumerate(methods):
        values = [
            int(
                next(
                    row["mr_count"]
                    for row in rows
                    if row["contract"] == contract and row["method"] == method
                )
            )
            for contract in contracts
        ]
        offset = (index - (len(methods) - 1) / 2) * width
        _bars(axis, x + offset, values, width, labels[method], _COLORS[index])
    axis.set_title("MR counts by construction method")
    axis.set_ylabel("Constructed MRs")
    _finish_grouped_axis(axis, x, contracts)
    _save(figure, destination)


def _figure_vulnerability_comparison(source: Path, destination: Path) -> None:
    rows = [
        row
        for row in _read_csv(source / "computed/vulnerability_totals.csv")
        if row["vulnerability_type"] != "Total"
    ]
    methods = ["MPSC", "VDMBSCMT", "Solhint", "Slither"]
    labels = {
        "compiler_version": "Compiler\nversion",
        "integer_overflow": "Overflow /\nunderflow",
        "reentrancy": "Reentrancy",
        "access_control": "Access\ncontrol",
        "short_address_attack": "Short\naddress",
    }
    x = np.arange(len(rows))
    width = 0.19
    figure, axis = plt.subplots(figsize=(10.5, 5.8))
    for index, method in enumerate(methods):
        values = [int(row[f"{method}_count"]) for row in rows]
        offset = (index - (len(methods) - 1) / 2) * width
        _bars(axis, x + offset, values, width, method, _COLORS[index])
    axis.set_title("Confirmed vulnerabilities by method")
    axis.set_ylabel("Confirmed findings")
    _finish_grouped_axis(axis, x, [labels[row["vulnerability_type"]] for row in rows])
    axis.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    _save(figure, destination)


def _figure_optimization(source: Path, destination: Path) -> None:
    rows = [
        row
        for row in _read_csv(source / "computed/optimization.csv")
        if row["contract"] != "Overall"
    ]
    contracts = [row["contract"] for row in rows]
    figure, axes = plt.subplots(1, 3, figsize=(15, 5.4))
    panels = [
        ("MR count", "mr_before", "mr_after"),
        (
            "Confirmed vulnerabilities",
            "vulnerabilities_before",
            "vulnerabilities_after",
        ),
        ("Execution time (s)", "time_before_seconds", "time_after_seconds"),
    ]
    x = np.arange(len(contracts))
    width = 0.36
    for axis, (title, before_key, after_key) in zip(axes, panels):
        before = [float(row[before_key]) for row in rows]
        after = [float(row[after_key]) for row in rows]
        _bars(axis, x - width / 2, before, width, "Before", _COLORS[0])
        _bars(axis, x + width / 2, after, width, "After", _COLORS[1])
        axis.legend(frameon=False, fontsize=8)
        axis.set_title(title)
        axis.set_xticks(x, contracts, rotation=28, ha="right")
        axis.grid(axis="y", alpha=0.2)
    figure.suptitle("MR-set optimization outcomes", fontsize=14)
    figure.tight_layout()
    _save(figure, destination)


def _figure_method_time(source: Path, destination: Path) -> None:
    rows = _read_csv(source / "method_time_comparison.csv")
    methods = [row["method"] for row in rows]
    times = [float(row["total_time_seconds"]) for row in rows]
    findings = [int(row["confirmed_vulnerabilities"]) for row in rows]
    x = np.arange(len(methods))

    figure, time_axis = plt.subplots(figsize=(9, 5.6))
    bars = time_axis.bar(x, times, color=_COLORS[0], width=0.58)
    time_axis.bar_label(bars, fmt="%.2f", padding=3, fontsize=8)
    time_axis.set_yscale("log")
    time_axis.set_ylabel("Total time (seconds, log scale)")
    time_axis.set_xticks(x, methods)
    time_axis.grid(axis="y", alpha=0.2)
    finding_axis = time_axis.twinx()
    finding_axis.plot(
        x,
        findings,
        color=_COLORS[1],
        marker="o",
        linewidth=2,
        label="Confirmed vulnerabilities",
    )
    finding_axis.set_ylabel("Confirmed vulnerabilities")
    finding_axis.set_ylim(0, max(findings) + 2)
    finding_axis.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    time_axis.set_title("Time overhead and confirmed findings")
    finding_axis.legend(frameon=False, loc="upper left")
    _save(figure, destination)


def _figure_mr_sensitivity(source: Path, destination: Path) -> None:
    rows = _read_csv(source / "mytoken_mr_sensitivity.csv")
    mr_ids = list(dict.fromkeys(row["mr_id"] for row in rows))
    markers = ["s", "o", "^", "v"]
    figure, axis = plt.subplots(figsize=(11, 5.8))
    for index, mr_id in enumerate(mr_ids):
        selected = [row for row in rows if row["mr_id"] == mr_id]
        axis.scatter(
            [int(row["mutant_index"]) for row in selected],
            [float(row["detection_rate"]) for row in selected],
            marker=markers[index],
            color=_COLORS[index],
            label=mr_id,
            s=28,
            alpha=0.85,
        )
    axis.set_title("MR sensitivity across 49 MyToken mutants")
    axis.set_xlabel("MyToken mutant index")
    axis.set_ylabel("Detection rate over 10 executions")
    axis.set_ylim(-0.04, 1.08)
    axis.legend(frameon=False, ncol=4)
    axis.grid(axis="y", alpha=0.2)
    _save(figure, destination)


def _figure_mrd_distribution(source: Path, destination: Path) -> None:
    rows = _read_csv(source / "mytoken_mrd_pairs.csv")
    labels = [f"{row['left_mr']} / {row['right_mr']}" for row in rows]
    values = [float(row["mrd"]) for row in rows]
    figure, axis = plt.subplots(figsize=(10, 5.8))
    bars = axis.barh(labels, values, color=_COLORS[2])
    axis.bar_label(bars, fmt="%.4f", padding=3)
    axis.set_xlim(0, 0.7)
    axis.set_xlabel("MR difference (MRD)")
    axis.set_title("Pairwise MR-difference distribution")
    axis.grid(axis="x", alpha=0.2)
    _save(figure, destination)


def _bars(
    axis: Any,
    positions: Any,
    values: list[float] | list[int],
    width: float,
    label: str,
    color: str,
) -> None:
    bars = axis.bar(positions, values, width, label=label, color=color)
    axis.bar_label(bars, padding=2, fontsize=8, fmt="%g")


def _finish_grouped_axis(axis: Any, x: Any, labels: list[str]) -> None:
    axis.set_xticks(x, labels, rotation=24, ha="right")
    axis.legend(frameon=False)
    axis.grid(axis="y", alpha=0.2)


def _save(figure: Any, destination: Path) -> None:
    figure.tight_layout()
    figure.savefig(destination, dpi=180, bbox_inches="tight")
    plt.close(figure)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))
