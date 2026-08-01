"""Runner helpers for experiments"""

from __future__ import annotations

import hashlib
import json

from ..models import (
    ContractState,
    ExecutionObservation,
    NativeBalances,
    TransactionInfo,
)


def dual_channel_execute(
    backend, contract_address, compile_result, function_name, args, sender, accs
):
    """Execute via eth_call + eth_sendTransaction"""
    # eth_call for μ
    try:
        return_value = backend.call_view(
            contract_address, compile_result.abi, function_name, args, sender
        )
    except Exception:
        return_value = None

    # Pre-state
    token_before = {}
    for i, acc in enumerate(accs[:2]):
        try:
            token_before[f"account_{i}"] = backend.call_view(
                contract_address, compile_result.abi, "getBalance", [acc], sender
            )
        except Exception:
            token_before[f"account_{i}"] = None

    # eth_sendTransaction
    try:
        result, receipt = backend.send_transaction(
            contract_address, compile_result.abi, function_name, args, sender
        )
        tx_success = receipt.success
        gas_used = receipt.gas_used
        tx_hash = receipt.tx_hash
    except Exception:
        tx_success = False
        gas_used = None
        tx_hash = None

    # Post-state
    token_after = {}
    for i, acc in enumerate(accs[:2]):
        try:
            token_after[f"account_{i}"] = backend.call_view(
                contract_address, compile_result.abi, "getBalance", [acc], sender
            )
        except Exception:
            token_after[f"account_{i}"] = None

    token_delta = {
        k: (token_after.get(k, 0) or 0) - (token_before.get(k, 0) or 0)
        for k in token_before
    }

    return ExecutionObservation(
        outcome_type="success_transaction" if tx_success else "evm_revert",
        execution_status="success" if tx_success else "evm_revert",
        return_value=return_value,
        transaction=TransactionInfo(
            submitted=True,
            hash=tx_hash,
            receipt_status=1 if tx_success else 0,
            gas_used=gas_used,
        ),
        native_balances=NativeBalances(),
        contract_state=ContractState(
            before={"token_balances": token_before},
            after={"token_balances": token_after},
            delta={"token_balances": token_delta},
        ),
    )


def state_hash(state: dict) -> str:
    canonical = json.dumps(state, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()
