"""Contract-operator scanner for all 16 operators x 4 contracts"""

from __future__ import annotations

import csv
import re
from pathlib import Path

# Mutation operators
OPERATORS = [
    {
        "id": "ROR",
        "name": "Relational Operator Replacement",
        "patterns": [r"[><=!]=?"],
        "elements": ["condition"],
    },
    {
        "id": "LOR",
        "name": "Logical Operator Replacement",
        "patterns": [r"&&", r"\|\|"],
        "elements": ["condition"],
    },
    {
        "id": "COR",
        "name": "Conditional Operator Replacement",
        "patterns": [r"&&\s*\|\|", r"\|\|\s*&&"],
        "elements": ["condition"],
    },
    {
        "id": "ASR",
        "name": "Assignment Short-cut Operator Replacement",
        "patterns": [r"[+\-*/]="],
        "elements": ["assignment"],
    },
    {
        "id": "SDL",
        "name": "Statement Deletion",
        "patterns": [r"^\s*[^/].*;$"],
        "elements": ["statement"],
    },
    {
        "id": "RSD",
        "name": "Require Statement Deletion",
        "patterns": [r"require\s*\("],
        "elements": ["require"],
    },
    {
        "id": "RVR",
        "name": "Return Value Replacement",
        "patterns": [r"return\s+(true|false|\d+)"],
        "elements": ["return"],
    },
    {
        "id": "VTR",
        "name": "Variable Type Keyword Replacement",
        "patterns": [r"uint\d*", r"int\d*", r"bytes\d*"],
        "elements": ["type"],
    },
    {
        "id": "DLR",
        "name": "Data Location Keyword Replacement",
        "patterns": [r"\bmemory\b", r"\bstorage\b", r"\bcalldata\b"],
        "elements": ["location"],
    },
    {
        "id": "EUR",
        "name": "Ether Unit Replacement",
        "patterns": [r"\bwei\b", r"\bfinney\b", r"\bszabo\b", r"\bether\b"],
        "elements": ["unit"],
    },
    {
        "id": "FVC",
        "name": "Function Visibility Keyword Change",
        "patterns": [r"\bpublic\b", r"\bprivate\b", r"\binternal\b", r"\bexternal\b"],
        "elements": ["visibility"],
    },
    {
        "id": "AVR",
        "name": "Address Variable Replacement",
        "patterns": [r"\bmsg\.sender\b", r"\btx\.origin\b", r"\bblock\.coinbase\b"],
        "elements": ["address"],
    },
    {
        "id": "GVC",
        "name": "Global Variable Change",
        "patterns": [r"\bblock\.timestamp\b", r"\bblock\.number\b", r"\bmsg\.value\b"],
        "elements": ["global"],
    },
    {
        "id": "FSC",
        "name": "Function State Keyword Change",
        "patterns": [r"\bview\b", r"\bpure\b", r"\bconstant\b"],
        "elements": ["mutability"],
    },
    {
        "id": "MFR",
        "name": "Mathematical Functions Replacement",
        "patterns": [r"\baddmod\b", r"\bmulmod\b"],
        "elements": ["math"],
    },
    {
        "id": "PKD",
        "name": "Payable Keyword Deletion",
        "patterns": [r"\bpayable\b"],
        "elements": ["payable"],
    },
]


def scan_contract_operators(contract_path: str) -> list[dict]:
    """Scan all 16 operators against a contract"""
    with open(contract_path, encoding="utf-8", errors="ignore") as f:
        content = f.read()
    lines = content.split("\n")

    results = []
    for op in OPERATORS:
        sites = []
        for i, line in enumerate(lines, 1):
            for pattern in op["patterns"]:
                if re.search(pattern, line):
                    sites.append({"line": i, "text": line.strip()[:80]})
                    break

        # Determine status
        if not op.get("patterns"):
            status = "definition_missing"
        elif not sites:
            status = "not_applicable"
        else:
            status = "applicable_sites_found"

        results.append(
            {
                "operator_id": op["id"],
                "operator_name": op["name"],
                "applicable": len(sites) > 0,
                "candidate_sites": len(sites),
                "status": status,
                "sites": sites[:5],  # First 5 sites for reference
            }
        )

    return results


def scan_all_contracts(contracts_config: str) -> dict:
    """Scan all contracts against all 16 operators"""
    import yaml

    with open(contracts_config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    all_results = []
    for contract_cfg in cfg["contracts"]:
        contract_id = contract_cfg["contract_id"]
        source_path = contract_cfg.get("repository_path")

        if not source_path or not Path(source_path).exists():
            for op in OPERATORS:
                all_results.append(
                    {
                        "contract_id": contract_id,
                        "operator_id": op["id"],
                        "status": "source_not_available",
                        "applicable": False,
                        "candidate_sites": 0,
                    }
                )
            continue

        op_results = scan_contract_operators(source_path)
        for r in op_results:
            all_results.append(
                {
                    "contract_id": contract_id,
                    **r,
                }
            )

    return {"results": all_results, "total": len(all_results)}


def generate_operator_coverage_csv(results: list[dict], output_path: str):
    """Generate contract-operator coverage CSV"""
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "contract_id",
                "operator_id",
                "operator_name",
                "applicable",
                "candidate_sites",
                "status",
            ],
        )
        writer.writeheader()
        for r in results:
            writer.writerow(
                {
                    k: r.get(k, "")
                    for k in [
                        "contract_id",
                        "operator_id",
                        "operator_name",
                        "applicable",
                        "candidate_sites",
                        "status",
                    ]
                }
            )
