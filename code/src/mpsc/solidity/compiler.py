"""Solidity compiler module for MPSC"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CompileResult:
    """Result of compiling a Solidity contract"""

    contract_name: str
    abi: list[dict] = field(default_factory=list)
    bytecode: str = ""
    bytecode_hex: str = ""
    compiler_version: str = ""
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    success: bool = True


def parse_pragma(content: str) -> str | None:
    """Extract pragma solidity version from source code"""
    match = re.search(r"pragma\s+solidity\s+([^;]+);", content)
    if match:
        return match.group(1).strip()
    return None


def normalize_pragma(pragma: str) -> str:
    """Normalize pragma version string"""
    # Remove ^, >=, etc.
    version = re.sub(r"[^0-9.]", "", pragma)
    return version


def find_compatible_solc(pragma: str, available_versions: list[str]) -> str | None:
    """Find a compatible solc version for the given pragma"""
    pragma_version = normalize_pragma(pragma)

    # Simple compatibility check
    for version in sorted(available_versions, reverse=True):
        if version >= pragma_version:
            return version

    return available_versions[-1] if available_versions else None


def compile_contract_solcx(
    source_path: str | Path,
    solc_version: str | None = None,
) -> CompileResult:
    """Compile a Solidity contract using py-solc-x"""
    source_path = Path(source_path)
    contract_name = source_path.stem

    try:
        from solcx import compile_source, install_solc, set_solc_version

        # Read source
        with open(source_path) as f:
            source = f.read()

        # Parse pragma if version not specified
        if solc_version is None:
            pragma = parse_pragma(source)
            if pragma:
                solc_version = normalize_pragma(pragma)
            else:
                solc_version = "0.4.25"  # default

        # Install solc if needed
        try:
            set_solc_version(solc_version)
        except Exception:
            install_solc(solc_version)
            set_solc_version(solc_version)

        # Compile
        compiled = compile_source(source, output_values=["abi", "bin"])

        # Extract contract data
        for key, value in compiled.items():
            if contract_name in key:
                return CompileResult(
                    contract_name=contract_name,
                    abi=value["abi"],
                    bytecode=value["bin"],
                    bytecode_hex="0x" + value["bin"],
                    compiler_version=solc_version,
                    success=True,
                )

        # If not found by name, take the first one
        for key, value in compiled.items():
            return CompileResult(
                contract_name=contract_name,
                abi=value["abi"],
                bytecode=value["bin"],
                bytecode_hex="0x" + value["bin"],
                compiler_version=solc_version,
                success=True,
            )

        return CompileResult(
            contract_name=contract_name,
            errors=["No contract found in source"],
            success=False,
        )

    except ImportError:
        return CompileResult(
            contract_name=contract_name,
            errors=["py-solc-x not installed. Run: pip install py-solc-x"],
            success=False,
        )
    except Exception as e:
        return CompileResult(
            contract_name=contract_name,
            errors=[str(e)],
            success=False,
        )


def load_abi(abi_path: str | Path) -> list[dict]:
    """Load ABI from a JSON file"""
    import json

    with open(abi_path) as f:
        return json.load(f)
