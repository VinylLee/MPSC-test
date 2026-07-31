"""Local chain backend using eth-tester for MPSC - refactored"""

from __future__ import annotations

from typing import Any

from eth_tester import EthereumTester, PyEVMBackend
from web3 import Web3

from ..models import (
    ContractState,
    ExecutionObservation,
    NativeBalances,
    TransactionInfo,
)
from ..testing.outcomes import classify_web3_error
from .backend import ChainBackend, ChainState, TransactionReceipt


class LocalChainBackend(ChainBackend):
    """Local chain backend using eth-tester"""

    def __init__(self) -> None:
        self._tester = EthereumTester(backend=PyEVMBackend())
        self._w3 = Web3(Web3.EthereumTesterProvider(self._tester))

    def get_accounts(self) -> list[str]:
        return [
            self._w3.to_checksum_address(acc) for acc in self._tester.get_accounts()
        ]

    def get_balance(self, address: str) -> int:
        return self._w3.eth.get_balance(self._w3.to_checksum_address(address))

    def _build_tx_params(
        self, sender: str, value: int = 0, gas_limit: int | None = None
    ) -> dict:
        return {
            "from": self._w3.to_checksum_address(sender),
            "value": value,
            "gas": gas_limit or 3000000,
            "gasPrice": self._w3.eth.gas_price,
            "nonce": self._w3.eth.get_transaction_count(
                self._w3.to_checksum_address(sender)
            ),
        }

    def deploy(
        self,
        bytecode: str,
        abi: list[dict],
        args: list[Any] | None = None,
        sender: str | None = None,
        value: int = 0,
        gas_limit: int | None = None,
    ) -> TransactionReceipt:
        if sender is None:
            sender = self.get_accounts()[0]

        contract = self._w3.eth.contract(abi=abi, bytecode=bytecode)
        if args:
            tx = contract.constructor(*args).build_transaction(
                self._build_tx_params(sender, value, gas_limit)
            )
        else:
            tx = contract.constructor().build_transaction(
                self._build_tx_params(sender, value, gas_limit)
            )

        tx_hash = self._w3.eth.send_transaction(tx)
        receipt = self._w3.eth.get_transaction_receipt(tx_hash)

        return TransactionReceipt(
            tx_hash=receipt["transactionHash"].hex(),
            contract_address=receipt.get("contractAddress"),
            gas_used=receipt["gasUsed"],
            success=receipt["status"] == 1,
            logs=[dict(log) for log in receipt.get("logs", [])],
        )

    def call_view(
        self,
        contract_address: str,
        abi: list[dict],
        function_name: str,
        args: list[Any] | None = None,
        caller: str | None = None,
    ) -> Any:
        if caller is None:
            caller = self.get_accounts()[0]
        contract = self._w3.eth.contract(
            address=self._w3.to_checksum_address(contract_address), abi=abi
        )
        func = contract.functions[function_name]
        call_args = {"from": self._w3.to_checksum_address(caller)}
        if args:
            return func(*args).call(call_args)
        return func().call(call_args)

    def call_raw(
        self,
        contract_address: str,
        calldata: bytes,
        caller: str | None = None,
    ) -> bytes:
        """Execute a read-only raw call, including fallback selectors."""

        if caller is None:
            caller = self.get_accounts()[0]
        result = self._w3.eth.call(
            {
                "from": self._w3.to_checksum_address(caller),
                "to": self._w3.to_checksum_address(contract_address),
                "data": "0x" + calldata.hex(),
            }
        )
        return bytes(result)

    def send_transaction(
        self,
        contract_address: str,
        abi: list[dict],
        function_name: str,
        args: list[Any] | None = None,
        sender: str | None = None,
        value: int = 0,
        gas_limit: int | None = None,
    ) -> tuple[Any, TransactionReceipt]:
        if sender is None:
            sender = self.get_accounts()[0]

        contract = self._w3.eth.contract(
            address=self._w3.to_checksum_address(contract_address), abi=abi
        )
        func = contract.functions[function_name]

        if args:
            built_tx = func(*args).build_transaction(
                self._build_tx_params(sender, value, gas_limit)
            )
        else:
            built_tx = func().build_transaction(
                self._build_tx_params(sender, value, gas_limit)
            )

        tx_hash = self._w3.eth.send_transaction(built_tx)
        receipt = self._w3.eth.get_transaction_receipt(tx_hash)

        result = None
        try:
            call_args = {"from": self._w3.to_checksum_address(sender)}
            result = func(*args).call(call_args) if args else func().call(call_args)
        except Exception:
            pass

        return result, TransactionReceipt(
            tx_hash=receipt["transactionHash"].hex(),
            contract_address=self._w3.to_checksum_address(contract_address),
            gas_used=receipt["gasUsed"],
            success=receipt["status"] == 1,
            logs=[dict(log) for log in receipt.get("logs", [])],
        )

    def execute_and_observe(
        self,
        contract_address: str,
        abi: list[dict],
        function_name: str,
        args: list[Any] | None = None,
        sender: str | None = None,
        value: int = 0,
        gas_limit: int | None = None,
        accounts_to_track: list[str] | None = None,
        is_view: bool = False,
    ) -> ExecutionObservation:
        """Execute and capture observation with strict namespace separation"""
        if sender is None:
            sender = self.get_accounts()[0]
        if accounts_to_track is None:
            accounts_to_track = []

        token_balances_before = {}
        native_before = {}
        for acc in accounts_to_track:
            acc_cs = self._w3.to_checksum_address(acc)
            native_before[acc] = self.get_balance(acc_cs)
            try:
                token_balances_before[acc] = self.call_view(
                    contract_address, abi, "getBalance", [acc_cs], sender
                )
            except Exception:
                token_balances_before[acc] = None

        if is_view:
            try:
                result = self.call_view(
                    contract_address, abi, function_name, args, sender
                )
                return ExecutionObservation(
                    outcome_type="success_view_call",
                    execution_status="success",
                    return_value=result,
                    transaction=TransactionInfo(submitted=False),
                    native_balances=NativeBalances(
                        before=native_before,
                        after=native_before,
                        delta={k: 0 for k in native_before},
                    ),
                    contract_state=ContractState(
                        before={"token_balances": token_balances_before},
                        after={"token_balances": token_balances_before},
                        delta={"token_balances": {k: 0 for k in token_balances_before}},
                    ),
                    events=[],
                    error=None,
                )
            except Exception as e:
                outcome = classify_web3_error(e)
                return ExecutionObservation(
                    outcome_type=outcome.value,
                    execution_status=outcome.value,
                    return_value=None,
                    transaction=TransactionInfo(submitted=False),
                    native_balances=NativeBalances(
                        before=native_before, after=native_before
                    ),
                    contract_state=ContractState(
                        before={"token_balances": token_balances_before}
                    ),
                    error={"type": type(e).__name__, "message": str(e)},
                )

        else:
            try:
                result, receipt = self.send_transaction(
                    contract_address, abi, function_name, args, sender, value, gas_limit
                )

                native_after = {}
                token_balances_after = {}
                for acc in accounts_to_track:
                    acc_cs = self._w3.to_checksum_address(acc)
                    native_after[acc] = self.get_balance(acc_cs)
                    try:
                        token_balances_after[acc] = self.call_view(
                            contract_address, abi, "getBalance", [acc_cs], sender
                        )
                    except Exception:
                        token_balances_after[acc] = None

                native_delta = {
                    k: native_after.get(k, 0) - native_before.get(k, 0)
                    for k in native_before
                }
                token_delta = {}
                for k in token_balances_before:
                    sb = token_balances_before.get(k, 0) or 0
                    fb = token_balances_after.get(k, 0) or 0
                    token_delta[k] = fb - sb

                return ExecutionObservation(
                    outcome_type="success_transaction"
                    if receipt.success
                    else "evm_revert",
                    execution_status="success" if receipt.success else "evm_revert",
                    return_value=result,
                    transaction=TransactionInfo(
                        submitted=True,
                        hash=receipt.tx_hash,
                        receipt_status=1 if receipt.success else 0,
                        gas_used=receipt.gas_used,
                    ),
                    native_balances=NativeBalances(
                        before=native_before, after=native_after, delta=native_delta
                    ),
                    contract_state=ContractState(
                        before={"token_balances": token_balances_before},
                        after={"token_balances": token_balances_after},
                        delta={"token_balances": token_delta},
                    ),
                    events=[],
                    error=None
                    if receipt.success
                    else {"type": "EVMRevert", "message": "Transaction reverted"},
                )
            except Exception as e:
                outcome = classify_web3_error(e)
                return ExecutionObservation(
                    outcome_type=outcome.value,
                    execution_status=outcome.value,
                    return_value=None,
                    transaction=TransactionInfo(submitted=False),
                    native_balances=NativeBalances(
                        before=native_before, after=native_before
                    ),
                    contract_state=ContractState(
                        before={"token_balances": token_balances_before}
                    ),
                    error={"type": type(e).__name__, "message": str(e)},
                )

    def execute_raw_and_observe(
        self,
        contract_address: str,
        abi: list[dict],
        calldata: bytes,
        sender: str,
        accounts_to_track: list[str] | None = None,
        gas_limit: int | None = None,
    ) -> ExecutionObservation:
        """Execute pre-encoded calldata while preserving the observation schema."""

        accounts_to_track = accounts_to_track or []
        address = self._w3.to_checksum_address(contract_address)
        sender = self._w3.to_checksum_address(sender)
        data = "0x" + calldata.hex()
        token_before: dict[str, Any] = {}
        native_before: dict[str, int] = {}
        for account in accounts_to_track:
            native_before[account] = self.get_balance(account)
            try:
                token_before[account] = self.call_view(
                    contract_address, abi, "getBalance", [account], sender
                )
            except Exception:
                token_before[account] = None

        return_value = None
        try:
            call_result = self._w3.eth.call(
                {"from": sender, "to": address, "data": data}
            )
            return_value = "0x" + bytes(call_result).hex()
        except Exception:
            pass

        try:
            tx_hash = self._w3.eth.send_transaction(
                {
                    **self._build_tx_params(sender, gas_limit=gas_limit),
                    "to": address,
                    "data": data,
                }
            )
            receipt = self._w3.eth.get_transaction_receipt(tx_hash)
            success = receipt["status"] == 1
            native_after: dict[str, int] = {}
            token_after: dict[str, Any] = {}
            for account in accounts_to_track:
                native_after[account] = self.get_balance(account)
                try:
                    token_after[account] = self.call_view(
                        contract_address, abi, "getBalance", [account], sender
                    )
                except Exception:
                    token_after[account] = None
            native_delta = {
                key: native_after[key] - native_before[key] for key in native_before
            }
            token_delta = {
                key: (token_after.get(key) or 0) - (token_before.get(key) or 0)
                for key in token_before
            }
            return ExecutionObservation(
                outcome_type="success_transaction" if success else "evm_revert",
                execution_status="success" if success else "evm_revert",
                return_value=return_value,
                transaction=TransactionInfo(
                    submitted=True,
                    hash=receipt["transactionHash"].hex(),
                    receipt_status=receipt["status"],
                    block_number=receipt["blockNumber"],
                    gas_used=receipt["gasUsed"],
                ),
                native_balances=NativeBalances(
                    before=native_before,
                    after=native_after,
                    delta=native_delta,
                ),
                contract_state=ContractState(
                    before={"token_balances": token_before},
                    after={"token_balances": token_after},
                    delta={"token_balances": token_delta},
                ),
                events=[dict(log) for log in receipt.get("logs", [])],
                error=(
                    None
                    if success
                    else {
                        "type": "EVMRevert",
                        "message": "Raw transaction reverted",
                    }
                ),
            )
        except Exception as error:
            outcome = classify_web3_error(error)
            return ExecutionObservation(
                outcome_type=outcome.value,
                execution_status=outcome.value,
                return_value=return_value,
                transaction=TransactionInfo(submitted=False),
                native_balances=NativeBalances(
                    before=native_before,
                    after=native_before,
                ),
                contract_state=ContractState(before={"token_balances": token_before}),
                error={"type": type(error).__name__, "message": str(error)},
            )

    def get_state(self, contract_address: str, abi: list[dict]) -> ChainState:
        contract_address = self._w3.to_checksum_address(contract_address)
        block = self._w3.eth.get_block("latest")
        return ChainState(block_number=block["number"], timestamp=block["timestamp"])

    def reset(self) -> None:
        self._tester = EthereumTester(backend=PyEVMBackend())
        self._w3 = Web3(Web3.EthereumTesterProvider(self._tester))

    def take_snapshot(self) -> int:
        return self._tester.take_snapshot()

    def revert_to_snapshot(self, snapshot_id: int) -> None:
        self._tester.revert_to_snapshot(snapshot_id)

    # Legacy interface
    def call(self, *args, **kwargs):
        return self.send_transaction(*args, **kwargs)
