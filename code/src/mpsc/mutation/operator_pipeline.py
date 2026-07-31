"""Truthful pipeline status for the 16 listed operators."""

from __future__ import annotations

import csv

from .musc import OPERATORS


def get_operator_pipeline_status() -> list[dict]:
    """Report the compatibility layer implementation status."""

    return [
        {
            "operator_id": operator.operator_id,
            "operator_name": operator.name,
            "definition_available": True,
            "scanner_implemented": True,
            "generator_implemented": True,
            "compile_validated": False,
            "used_in_canonical_matrix": False,
        }
        for operator in OPERATORS.values()
    ]


def write_operator_pipeline_csv(output_path: str) -> None:
    results = get_operator_pipeline_status()
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
