"""Full mutant generator using all implemented operators"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .extended_operators import EXTENDED_GENERATORS
from .operators import OPERATORS


def generate_all_mutants_for_contract(
    contract_id: str,
    source_path: str,
    output_dir: str | Path,
) -> dict:
    """Generate all possible mutants for a contract using all implemented operators"""
    output_dir = Path(output_dir) / contract_id
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(source_path, encoding="utf-8", errors="ignore") as f:
        source = f.read()

    source_sha = hashlib.sha256(source.encode()).hexdigest()
    source_filename = Path(source_path).name

    results = []

    # Run extended generators (FVC, AVR, FSC)
    for op_id, generator in EXTENDED_GENERATORS.items():
        sites = generator.find_sites(source)
        for site_idx, site in enumerate(sites):
            variants = generator.generate(source, site)
            for var_suffix, original, mutated in variants:
                mutant_id = f"{op_id}-S{site_idx + 1:02d}-{var_suffix}"
                mutant_dir = output_dir / mutant_id
                mutant_dir.mkdir(parents=True, exist_ok=True)

                # Write mutant source
                mutant_file = mutant_dir / source_filename
                lines = source.split("\n")
                lines[site.line - 1] = mutated
                mutant_source = "\n".join(lines)

                with open(mutant_file, "w", encoding="utf-8") as f:
                    f.write(mutant_source)

                mutant_sha = hashlib.sha256(mutant_source.encode()).hexdigest()

                # Write manifest
                manifest = {
                    "mutant_id": mutant_id,
                    "operator_id": op_id,
                    "site_id": f"S{site_idx + 1:02d}",
                    "contract_id": contract_id,
                    "source_file": source_path,
                    "source_sha256": source_sha,
                    "mutant_sha256": mutant_sha,
                    "line": site.line,
                    "original_text": original,
                    "mutated_text": mutated,
                    "aligned": True,
                    "generation_success": True,
                    "compile_success": None,
                }

                with open(mutant_dir / "manifest.json", "w") as f:
                    json.dump(manifest, f, indent=2)

                results.append(manifest)

    # Run basic operators (ROR, SDL, RVR, ASR, LOR)
    for op_id, operator in OPERATORS.items():
        if op_id in EXTENDED_GENERATORS:
            continue  # Already handled

        # Find sites using regex
        sites = _find_sites_for_operator(source, op_id)
        for site_idx, site in enumerate(sites):
            mutant_id = f"{op_id}-S{site_idx + 1:02d}-V01"
            mutant_dir = output_dir / mutant_id
            mutant_dir.mkdir(parents=True, exist_ok=True)

            # Apply mutation
            mutated, success = operator.apply(
                source, site["line"], site["original"], site["mutated"]
            )
            if not success:
                continue

            mutant_file = mutant_dir / source_filename
            with open(mutant_file, "w", encoding="utf-8") as f:
                f.write(mutated)

            mutant_sha = hashlib.sha256(mutated.encode()).hexdigest()

            manifest = {
                "mutant_id": mutant_id,
                "operator_id": op_id,
                "site_id": f"S{site_idx + 1:02d}",
                "contract_id": contract_id,
                "source_file": source_path,
                "source_sha256": source_sha,
                "mutant_sha256": mutant_sha,
                "line": site["line"],
                "original_text": site["original"],
                "mutated_text": site["mutated"],
                "aligned": True,
                "generation_success": True,
                "compile_success": None,
            }

            with open(mutant_dir / "manifest.json", "w") as f:
                json.dump(manifest, f, indent=2)

            results.append(manifest)

    return {
        "contract_id": contract_id,
        "source_sha256": source_sha,
        "total_generated": len(results),
        "mutants": results,
    }


def _find_sites_for_operator(source: str, op_id: str) -> list[dict]:
    """Find mutation sites for basic operators"""
    import re

    sites = []
    lines = source.split("\n")

    if op_id == "ROR":
        for i, line in enumerate(lines, 1):
            matches = re.finditer(r"([><=!]=?)", line)
            for m in matches:
                sites.append(
                    {
                        "line": i,
                        "original": m.group(1),
                        "mutated": _flip_operator(m.group(1)),
                        "context": line.strip()[:80],
                    }
                )

    elif op_id == "SDL":
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if (
                stripped
                and not stripped.startswith("//")
                and not stripped.startswith("/*")
                and ";" in stripped
            ):
                sites.append(
                    {
                        "line": i,
                        "original": stripped,
                        "mutated": f"// {stripped}",
                        "context": stripped[:80],
                    }
                )

    elif op_id == "RVR":
        for i, line in enumerate(lines, 1):
            if "return true" in line:
                sites.append(
                    {
                        "line": i,
                        "original": "return true;",
                        "mutated": "return false;",
                        "context": line.strip()[:80],
                    }
                )
            elif "return false" in line:
                sites.append(
                    {
                        "line": i,
                        "original": "return false;",
                        "mutated": "return true;",
                        "context": line.strip()[:80],
                    }
                )

    elif op_id == "ASR":
        for i, line in enumerate(lines, 1):
            for op in ["+=", "-=", "*=", "/="]:
                if op in line:
                    alt = {"+=": "-=", "-=": "+=", "*=": "/=", "/=": "*="}[op]
                    sites.append(
                        {
                            "line": i,
                            "original": op,
                            "mutated": alt,
                            "context": line.strip()[:80],
                        }
                    )

    elif op_id == "LOR":
        for i, line in enumerate(lines, 1):
            if "&&" in line:
                sites.append(
                    {
                        "line": i,
                        "original": "&&",
                        "mutated": "||",
                        "context": line.strip()[:80],
                    }
                )
            elif "||" in line:
                sites.append(
                    {
                        "line": i,
                        "original": "||",
                        "mutated": "&&",
                        "context": line.strip()[:80],
                    }
                )

    return sites


def _flip_operator(op: str) -> str:
    """Flip a relational operator"""
    flips = {
        ">": "<=",
        "<=": ">",
        "<": ">=",
        ">=": "<",
        "==": "!=",
        "!=": "==",
    }
    return flips.get(op, op)
