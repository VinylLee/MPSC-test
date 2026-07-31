"""Regenerate aggregate tables from the published normalized CSVs."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any

TABLE_FILES = [
    "mutants.csv",
    "mutation_scores.csv",
    "llm_effectiveness.csv",
    "llm_efficiency.csv",
    "target_vulnerabilities.csv",
    "vulnerability_totals.csv",
    "optimization.csv",
]


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _number(value: float) -> str:
    return str(round(value, 6))


def generate_computed_tables(
    *,
    input_dir: str | Path = "experiment-data/processed",
    output_dir: str | Path = "experiment-data/runs/tables",
) -> dict[str, Any]:
    """Write all seven aggregate tables without changing published evidence."""

    source = Path(input_dir)
    output = Path(output_dir)
    builders = [
        _table_3,
        _table_4,
        _table_5,
        _table_6,
        _table_7,
        _table_8,
        _table_9,
    ]
    generated = []
    for filename, builder in zip(TABLE_FILES, builders):
        rows = builder(source)
        destination = output / filename
        _write(destination, rows)
        generated.append(
            {
                "path": destination.as_posix(),
                "row_count": len(rows),
                "input_dir": source.as_posix(),
            }
        )
    return {
        "schema_version": 1,
        "evidence_class": "computed",
        "table_count": len(generated),
        "tables": generated,
    }


def _table_3(source: Path) -> list[dict[str, Any]]:
    rows = []
    totals = [0, 0, 0]
    for item in _read(source / "mutant_counts.csv"):
        values = [
            int(item["generated_mutants"]),
            int(item["equivalent_mutants"]),
            int(item["valid_mutants"]),
        ]
        totals = [left + right for left, right in zip(totals, values)]
        rows.append(
            {
                "contract": item["contract"],
                "generated_mutants": values[0],
                "equivalent_mutants": values[1],
                "valid_mutants": values[2],
                "count_invariant": values[0] == values[1] + values[2],
                "source_path": item["source_path"],
                "source_locator": item["source_locator"],
            }
        )
    rows.append(
        {
            "contract": "Overall",
            "generated_mutants": totals[0],
            "equivalent_mutants": totals[1],
            "valid_mutants": totals[2],
            "count_invariant": totals[0] == totals[1] + totals[2],
            "source_path": "derived from mutant_counts.csv",
            "source_locator": "all rows",
        }
    )
    return rows


def _table_4(source: Path) -> list[dict[str, Any]]:
    rows = []
    source_rows = _read(source / "mutation_scores.csv")
    for item in source_rows:
        computed = 100 * int(item["killed_mutants"]) / int(item["valid_mutants"])
        rows.append(
            {
                "contract": item["contract"],
                "tc_per_mr": item["tc_per_mr"],
                "source_test_case_count": item["source_test_case_count"],
                "killed_mutants": item["killed_mutants"],
                "valid_mutants": item["valid_mutants"],
                "mutation_score_percent": _number(computed),
                "source_path": item["source_path"],
                "source_locator": item["source_locator"],
            }
        )
    computed_average = sum(
        float(item["mutation_score_percent"]) for item in source_rows
    ) / len(source_rows)
    rows.append(
        {
            "contract": "Overall",
            "tc_per_mr": "all budgets",
            "source_test_case_count": sum(
                int(item["source_test_case_count"]) for item in source_rows
            ),
            "killed_mutants": "",
            "valid_mutants": "",
            "mutation_score_percent": _number(computed_average),
            "source_path": "derived from mutation_scores.csv",
            "source_locator": "all 15 rows",
        }
    )
    return rows


def _table_5(source: Path) -> list[dict[str, Any]]:
    rows = []
    computed_values: list[tuple[float, float, float]] = []
    for item in _read(source / "llm_identification.csv"):
        truth = int(item["ground_truth_count"])
        identified = int(item["llm_identified_count"])
        true_positive = int(item["true_positive"])
        precision = 100 * true_positive / identified
        recall = 100 * true_positive / truth
        f1 = 2 * precision * recall / (precision + recall)
        computed_values.append((precision, recall, f1))
        rows.append(
            {
                "contract": item["contract"],
                "ground_truth_count": truth,
                "llm_identified_count": identified,
                "true_positive": true_positive,
                "precision_percent": _number(precision),
                "recall_percent": _number(recall),
                "f1_percent": _number(f1),
                "source_path": item["source_path"],
                "source_locator": item["source_locator"],
            }
        )
    averages = [
        sum(values[index] for values in computed_values) / len(computed_values)
        for index in range(3)
    ]
    rows.append(
        {
            "contract": "Average",
            "ground_truth_count": "",
            "llm_identified_count": "",
            "true_positive": "",
            "precision_percent": _number(averages[0]),
            "recall_percent": _number(averages[1]),
            "f1_percent": _number(averages[2]),
            "source_path": "derived from llm_identification.csv",
            "source_locator": "all five rows",
        }
    )
    return rows


def _table_6(source: Path) -> list[dict[str, Any]]:
    source_rows = _read(source / "llm_efficiency.csv")
    by_metric = {row["metric"]: row for row in source_rows}
    manual = float(by_metric["manual_identification"]["value"])
    llm = float(by_metric["llm_assisted_identification"]["value"])
    computed = 100 * (manual - llm) / manual
    return [
        {
            "manual_minutes": _number(manual),
            "llm_minutes": _number(llm),
            "efficiency_gain_percent": _number(computed),
            "source_path": by_metric["efficiency_gain"]["source_path"],
            "source_locator": "tab:rq4_efficiency",
        }
    ]


def _table_7(source: Path) -> list[dict[str, Any]]:
    targets = {
        "MyToken": "short_address_attack",
        "Rubixi": "access_control",
        "BecToken": "integer_overflow",
        "PERSONAL_BANK": "reentrancy",
    }
    source_rows = _read(source / "vulnerability_findings.csv")
    rows = []
    for contract, vulnerability in targets.items():
        for method in ("MPSC", "VDMBSCMT", "Solhint", "Slither"):
            item = next(
                row
                for row in source_rows
                if row["contract"] == contract
                and row["vulnerability_type"] == vulnerability
                and row["method"] == method
            )
            rows.append(
                {
                    "contract": contract,
                    "target_vulnerability": vulnerability,
                    "method": method,
                    "confirmed_count": item["confirmed_count"],
                    "source_path": "data\\processed\\vulnerability_findings.csv",
                    "source_locator": (
                        f"contract={contract}; vulnerability={vulnerability}; "
                        f"method={method}"
                    ),
                }
            )
    return rows


def _table_8(source: Path) -> list[dict[str, Any]]:
    methods = ("MPSC", "VDMBSCMT", "Solhint", "Slither")
    totals: dict[str, dict[str, int]] = defaultdict(
        lambda: {method: 0 for method in methods}
    )
    for item in _read(source / "vulnerability_findings.csv"):
        totals[item["vulnerability_type"]][item["method"]] += int(
            item["confirmed_count"]
        )
    rows = []
    for vulnerability in (
        "compiler_version",
        "integer_overflow",
        "reentrancy",
        "access_control",
        "short_address_attack",
    ):
        counts = totals[vulnerability]
        rows.append(
            {
                "vulnerability_type": vulnerability,
                **{f"{method}_count": counts[method] for method in methods},
                "extra_by_mpsc": counts["MPSC"]
                - max(counts[method] for method in methods[1:]),
                "source_path": "data\\processed\\vulnerability_findings.csv",
                "source_locator": f"vulnerability={vulnerability}",
            }
        )
    all_counts = {
        method: sum(values[method] for values in totals.values()) for method in methods
    }
    rows.append(
        {
            "vulnerability_type": "Total",
            **{f"{method}_count": all_counts[method] for method in methods},
            "extra_by_mpsc": all_counts["MPSC"]
            - max(all_counts[method] for method in methods[1:]),
            "source_path": "data\\processed\\vulnerability_findings.csv",
            "source_locator": "all rows",
        }
    )
    return rows


def _table_9(source: Path) -> list[dict[str, Any]]:
    rows = []
    source_rows = _read(source / "optimization_metrics.csv")
    for item in source_rows:
        rows.append(
            {
                "contract": item["contract"],
                "mr_before": item["mr_before"],
                "mr_after": item["mr_after"],
                "vulnerabilities_before": item["office_vulnerabilities_before"],
                "vulnerabilities_after": item["office_vulnerabilities_after"],
                "time_before_seconds": item["time_before_seconds"],
                "time_after_seconds": item["time_after_seconds"],
                "time_delta_percent": item["time_delta_percent_computed"],
                "mrd_before": item["mrd_before"],
                "mrd_after": item["mrd_after"],
                "mutation_score_before": item["mutation_score_before"],
                "mutation_score_after": item["mutation_score_after"],
                "source_path": item["source_path"],
                "source_locator": item["source_locator"],
            }
        )
    count = len(source_rows)
    before_time = sum(float(item["time_before_seconds"]) for item in source_rows)
    after_time = sum(float(item["time_after_seconds"]) for item in source_rows)
    rows.append(
        {
            "contract": "Overall",
            "mr_before": sum(int(item["mr_before"]) for item in source_rows),
            "mr_after": sum(int(item["mr_after"]) for item in source_rows),
            "vulnerabilities_before": sum(
                int(item["office_vulnerabilities_before"]) for item in source_rows
            ),
            "vulnerabilities_after": sum(
                int(item["office_vulnerabilities_after"]) for item in source_rows
            ),
            "time_before_seconds": _number(before_time / count),
            "time_after_seconds": _number(after_time / count),
            "time_delta_percent": _number(
                sum(float(item["time_delta_percent_computed"]) for item in source_rows)
                / count
            ),
            "mrd_before": "",
            "mrd_after": "",
            "mutation_score_before": "",
            "mutation_score_after": "",
            "source_path": "derived from optimization_metrics.csv",
            "source_locator": "all five rows",
        }
    )
    return rows
