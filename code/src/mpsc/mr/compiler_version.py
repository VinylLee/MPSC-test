"""Compiler version management for MR1"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ..solidity.compiler import compile_contract_solcx


@dataclass
class CompilerArtifact:
    solc_version: str
    compile_success: bool
    abi: list | None = None
    bytecode: str | None = None
    warnings: list[str] | None = None
    errors: list[str] | None = None
    bytecode_hash: str | None = None


def compile_with_version(source_path: str, solc_version: str) -> CompilerArtifact:
    """Compile a contract with a specific solc version"""
    try:
        result = compile_contract_solcx(source_path, solc_version)
        bytecode_hash = (
            hashlib.sha256(result.bytecode.encode()).hexdigest()[:16]
            if result.bytecode
            else None
        )
        return CompilerArtifact(
            solc_version=solc_version,
            compile_success=result.success,
            abi=result.abi if result.success else None,
            bytecode=result.bytecode if result.success else None,
            warnings=result.warnings,
            errors=result.errors if not result.success else None,
            bytecode_hash=bytecode_hash,
        )
    except Exception as e:
        return CompilerArtifact(
            solc_version=solc_version,
            compile_success=False,
            errors=[str(e)],
        )


def execute_mr1(mr_config: dict, source_path: str) -> dict:
    """Execute a single MR1 relation"""
    mr_id = mr_config["id"]
    source_solc = mr_config["source_solc"]
    followup_solc = mr_config["followup_solc"]

    # Compile with both versions
    source_artifact = compile_with_version(source_path, source_solc)
    followup_artifact = compile_with_version(source_path, followup_solc)

    # Check compilation results
    if not source_artifact.compile_success and not followup_artifact.compile_success:
        return {
            "mr_id": mr_id,
            "verdict": "unsupported",
            "blocking_reason": f"Both versions failed: {source_solc}, {followup_solc}",
            "source_compile": False,
            "followup_compile": False,
        }

    if not source_artifact.compile_success:
        return {
            "mr_id": mr_id,
            "verdict": "unsupported",
            "blocking_reason": f"Source compilation failed: {source_solc}",
            "source_compile": False,
            "followup_compile": followup_artifact.compile_success,
        }

    if not followup_artifact.compile_success:
        # MR1.3, MR1.5: one compiles, other doesn't
        return {
            "mr_id": mr_id,
            "verdict": "violation"
            if mr_config.get("predicates", {}).get("mu") == "mu_f != mu_s"
            else "pass",
            "source_compile": True,
            "followup_compile": False,
            "source_bytecode_hash": source_artifact.bytecode_hash,
            "followup_bytecode_hash": None,
            "explanation": (
                f"Source compiles with {source_solc}, "
                f"followup fails with {followup_solc}"
            ),
        }

    # Both compile - deploy and execute
    from ..chain.local_backend import LocalChainBackend
    from ..experiments.runner_helpers import dual_channel_execute
    from ..models import InputRelation, MetamorphicRelation, OutputRelation
    from ..testing.oracle import MRChecker

    # Deploy source
    backend_s = LocalChainBackend()
    accs_s = backend_s.get_accounts()
    receipt_s = backend_s.deploy(
        bytecode=source_artifact.bytecode, abi=source_artifact.abi, sender=accs_s[0]
    )

    # Deploy followup
    backend_f = LocalChainBackend()
    accs_f = backend_f.get_accounts()
    receipt_f = backend_f.deploy(
        bytecode=followup_artifact.bytecode, abi=followup_artifact.abi, sender=accs_f[0]
    )

    # Execute same function on both
    source_obs = dual_channel_execute(
        backend_s,
        receipt_s.contract_address,
        source_artifact,
        "sendCoin",
        [accs_s[1], 100],
        accs_s[0],
        accs_s,
    )
    followup_obs = dual_channel_execute(
        backend_f,
        receipt_f.contract_address,
        followup_artifact,
        "sendCoin",
        [accs_f[1], 100],
        accs_f[0],
        accs_f,
    )

    # Oracle
    mr = MetamorphicRelation(
        mr_id=mr_id,
        category="MR1",
        target_operation="contractCompiler",
        input_relation=InputRelation(description="", transform=""),
        output_relation=OutputRelation(description="", check_type="mr6_amount"),
    )
    oracle = MRChecker().check(mr, source_obs, followup_obs)

    return {
        "mr_id": mr_id,
        "category": "MR1",
        "source_solc": source_solc,
        "followup_solc": followup_solc,
        "source_compile": True,
        "followup_compile": True,
        "source_bytecode_hash": source_artifact.bytecode_hash,
        "followup_bytecode_hash": followup_artifact.bytecode_hash,
        "bytecode_same": source_artifact.bytecode_hash
        == followup_artifact.bytecode_hash,
        "source_return": source_obs.return_value,
        "followup_return": followup_obs.return_value,
        "source_gas": source_obs.transaction.gas_used,
        "followup_gas": followup_obs.transaction.gas_used,
        "verdict": oracle.verdict,
        "explanation": oracle.explanation,
    }
