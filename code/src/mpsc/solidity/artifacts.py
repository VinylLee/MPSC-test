"""Solidity artifacts module for MPSC"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CompilationArtifacts:
    """Compilation artifacts for a contract"""

    contract_name: str
    abi: list[dict] = field(default_factory=list)
    bytecode: str = ""
    source_hash: str = ""
    compiler_version: str = ""

    def save(self, output_dir: str | Path) -> Path:
        """Save artifacts to directory"""
        import json

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save ABI
        abi_path = output_dir / f"{self.contract_name}_abi.json"
        with open(abi_path, "w") as f:
            json.dump(self.abi, f, indent=2)

        # Save bytecode
        bytecode_path = output_dir / f"{self.contract_name}_bytecode.txt"
        with open(bytecode_path, "w") as f:
            f.write(self.bytecode)

        return output_dir
