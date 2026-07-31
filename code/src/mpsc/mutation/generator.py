"""Mutant generator for MPSC"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from .operators import OPERATORS


def generate_mutants(config_path: str) -> list[dict]:
    """Generate all mutants from config"""
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    source_path = cfg["contract"]
    output_dir = Path(cfg["output_dir"])

    with open(source_path, encoding="utf-8") as f:
        source_code = f.read()

    source_sha = hashlib.sha256(source_code.encode()).hexdigest()

    results = []
    for mutant_cfg in cfg["mutants"]:
        result = generate_single_mutant(
            mutant_cfg, source_code, source_sha, source_path, output_dir
        )
        results.append(result)

    return results


def generate_single_mutant(
    mutant_cfg: dict,
    source_code: str,
    source_sha: str,
    source_path: str,
    output_dir: Path,
) -> dict:
    """Generate a single mutant"""
    mutant_id = mutant_cfg["id"]
    operator_id = mutant_cfg["operator"]
    line = mutant_cfg["line"]
    original = mutant_cfg["original"]
    mutated = mutant_cfg["mutated"]

    operator = OPERATORS.get(operator_id)
    if not operator:
        return {
            "mutant_id": mutant_id,
            "generation_success": False,
            "error": f"Unknown operator: {operator_id}",
        }

    mutated_code, success = operator.apply(source_code, line, original, mutated)

    if not success:
        return {
            "mutant_id": mutant_id,
            "generation_success": False,
            "error": f"Could not apply mutation at line {line}",
        }

    mutant_sha = hashlib.sha256(mutated_code.encode()).hexdigest()

    # Write mutant
    mutant_dir = output_dir / mutant_id
    mutant_dir.mkdir(parents=True, exist_ok=True)

    source_filename = Path(source_path).name
    mutant_file = mutant_dir / source_filename
    with open(mutant_file, "w", encoding="utf-8") as f:
        f.write(mutated_code)

    # Write manifest
    manifest = {
        "mutant_id": mutant_id,
        "source_contract": source_path,
        "source_sha256": source_sha,
        "mutant_sha256": mutant_sha,
        "operator": operator_id,
        "source_type": mutant_cfg.get("source_type", "engineering_mutant"),
        "line": line,
        "original_text": original,
        "mutated_text": mutated,
        "description": mutant_cfg.get("description", ""),
        "expected_impact": mutant_cfg.get("expected_impact", ""),
        "generation_success": True,
        "compile_success": None,
        "mutant_file": str(mutant_file),
    }

    manifest_file = mutant_dir / "manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return manifest
