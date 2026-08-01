"""Contract loader module for MPSC"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .compiler import CompileResult, compile_contract_solcx, parse_pragma


@dataclass
class ContractInfo:
    """Information about a loaded contract"""

    name: str
    source_path: Path
    compile_result: CompileResult | None = None
    pragma: str | None = None

    @property
    def abi(self) -> list[dict]:
        if self.compile_result:
            return self.compile_result.abi
        return []

    @property
    def bytecode(self) -> str:
        if self.compile_result:
            return self.compile_result.bytecode
        return ""


def load_contract(
    source_path: str | Path, solc_version: str | None = None
) -> ContractInfo:
    """Load and compile a Solidity contract"""
    source_path = Path(source_path)

    # Read source to get pragma
    with open(source_path) as f:
        source = f.read()

    pragma = parse_pragma(source)

    # Compile
    compile_result = compile_contract_solcx(source_path, solc_version)

    return ContractInfo(
        name=source_path.stem,
        source_path=source_path,
        compile_result=compile_result,
        pragma=pragma,
    )


def list_contracts(directory: str | Path) -> list[Path]:
    """List all Solidity contracts in a directory"""
    directory = Path(directory)
    return sorted(directory.glob("**/*.sol"))
