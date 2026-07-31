"""Tests for the semantics-aware canonical executor."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from mpsc.models import (
    ContractState,
    ExecutionObservation,
    TransactionInfo,
)
from mpsc.mr import MRInstance, MRTemplate
from mpsc.solidity.compiler import CompileResult
from mpsc.testing.canonical_executor import CanonicalExecutor

ABI = [
    {
        "type": "function",
        "name": "sendCoin",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "_receiver", "type": "address"},
            {"name": "_amount", "type": "uint256"},
        ],
        "outputs": [{"name": "sufficient", "type": "bool"}],
    }
]
ACCOUNT_0 = "0x0000000000000000000000000000000000000001"
ACCOUNT_1 = "0x0000000000000000000000000000000000000002"


class FakeBackend:
    created = 0

    def __init__(self):
        type(self).created += 1
        self.snapshot_taken = False
        self.snapshot_reverted = False

    def get_accounts(self):
        return [ACCOUNT_0, ACCOUNT_1]

    def deploy(self, **_kwargs):
        return SimpleNamespace(
            success=True,
            contract_address="0x0000000000000000000000000000000000000003",
            tx_hash="0x1234",
            gas_used=100000,
        )

    def execute_and_observe(self, **kwargs):
        amount = kwargs["args"][1]
        return ExecutionObservation(
            execution_status="success",
            return_value=True,
            transaction=TransactionInfo(submitted=True, gas_used=21000),
            contract_state=ContractState(
                delta={
                    "token_balances": {
                        ACCOUNT_0: -amount,
                        ACCOUNT_1: amount,
                    }
                }
            ),
        )

    def take_snapshot(self):
        self.snapshot_taken = True
        return 7

    def revert_to_snapshot(self, snapshot_id):
        assert snapshot_id == 7
        self.snapshot_reverted = True

    def execute_raw_and_observe(self, **kwargs):
        return ExecutionObservation(
            execution_status="success",
            return_value=kwargs["calldata"].hex(),
            transaction=TransactionInfo(submitted=True, gas_used=22000),
            contract_state=ContractState(delta={"token_balances": {}}),
        )


def semantic_fixture(state_strategy="fresh_deployment"):
    template = MRTemplate(
        mr_id="MR6.1",
        category="MR6",
        target_operation="sendCoin",
        execution_primitive="amount_transform",
        mutable_parameters=("amount",),
        required_predicates=("mr6_amount",),
        evidence_sources=("mpsc.registry:MR6.1",),
        status="supported",
    )
    instance = MRInstance(
        instance_id="mytoken.MR6.1.sendCoin.v01",
        template_id="MR6.1",
        contract_id="mytoken",
        function="sendCoin",
        parameter_bindings={"_receiver": "address", "_amount": "uint256"},
        source_input={"_receiver": ACCOUNT_1, "_amount": 100},
        transformation={"name": "subtract_from_constant", "constant": 1000},
        followup_input={"_receiver": ACCOUNT_1, "_amount": 900},
        observers=("return_value", "contract_state.token_balances"),
        predicates=("mr6_amount",),
        predicate_spec={"mu": "mu_f == mu_s"},
        evidence_sources=("mpsc.registry:MR6.1",),
        status="resolved",
    )
    pair = instance.to_test_case_pair(state_strategy=state_strategy, seed=1)
    artifact = CompileResult(
        contract_name="MyToken",
        abi=ABI,
        bytecode="6000",
        compiler_version="0.4.11",
        success=True,
    )
    return template, instance, pair, artifact


def test_fresh_deployment_executes_both_cases_and_oracle():
    FakeBackend.created = 0
    template, instance, pair, artifact = semantic_fixture()

    result = CanonicalExecutor(backend_factory=FakeBackend).execute(
        template, instance, pair, artifact
    )

    assert result.status == "completed"
    assert result.binding is not None and result.binding.valid
    assert result.source_observation is not None
    assert result.followup_observation is not None
    assert result.oracle_result is not None
    assert result.verdict == result.oracle_result.verdict
    assert FakeBackend.created == 2


def test_identity_mismatch_is_rejected_before_backend_execution():
    FakeBackend.created = 0
    template, instance, pair, artifact = semantic_fixture()
    pair.template_id = "MR6.2"

    result = CanonicalExecutor(backend_factory=FakeBackend).execute(
        template, instance, pair, artifact
    )

    assert result.status == "invalid_binding"
    assert result.verdict is None
    assert FakeBackend.created == 0


@pytest.mark.parametrize("case_name", ["source", "followup"])
def test_source_and_followup_inputs_cannot_be_replaced_or_ignored(case_name):
    FakeBackend.created = 0
    template, instance, pair, artifact = semantic_fixture()
    getattr(pair, case_name).inputs["_amount"] += 1

    result = CanonicalExecutor(backend_factory=FakeBackend).execute(
        template, instance, pair, artifact
    )

    assert result.status == "invalid_binding"
    assert result.verdict is None
    assert FakeBackend.created == 0


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("instance_id", "mytoken.MR6.2.sendCoin.v01"),
        ("function", "getBalance"),
    ],
)
def test_pair_instance_id_and_function_are_not_ignored(field_name, bad_value):
    FakeBackend.created = 0
    template, instance, pair, artifact = semantic_fixture()
    setattr(pair, field_name, bad_value)

    result = CanonicalExecutor(backend_factory=FakeBackend).execute(
        template, instance, pair, artifact
    )

    assert result.status == "invalid_binding"
    assert result.verdict is None
    assert FakeBackend.created == 0


def test_unknown_specialized_route_is_explicitly_unsupported_not_pass():
    FakeBackend.created = 0
    template, instance, pair, artifact = semantic_fixture()
    template.execution_primitive = "deployment_env_transform"

    result = CanonicalExecutor(backend_factory=FakeBackend).execute(
        template, instance, pair, artifact
    )

    assert result.status == "unsupported"
    assert result.route == "deployment_environment"
    assert result.verdict is None
    assert FakeBackend.created == 0


def test_oracle_is_the_only_source_of_a_completed_verdict():
    template, instance, pair, artifact = semantic_fixture()

    class SentinelChecker:
        def check(self, relation, source, followup):
            from mpsc.models import OracleResult

            assert relation.mr_id == template.mr_id
            assert source is not None
            assert followup is not None
            return OracleResult(
                verdict="violation",
                violation=True,
                explanation="sentinel Oracle result",
            )

    result = CanonicalExecutor(
        backend_factory=FakeBackend,
        checker=SentinelChecker(),
    ).execute(template, instance, pair, artifact)

    assert result.status == "completed"
    assert result.verdict == "violation"
    assert result.verdict == result.oracle_result.verdict


def test_snapshot_strategy_reuses_one_backend_and_reverts():
    FakeBackend.created = 0
    instances = []

    def backend_factory():
        backend = FakeBackend()
        instances.append(backend)
        return backend

    template, instance, pair, artifact = semantic_fixture("snapshot_revert")
    result = CanonicalExecutor(backend_factory=backend_factory).execute(
        template, instance, pair, artifact
    )

    assert result.status == "completed"
    assert len(instances) == 1
    assert instances[0].snapshot_taken
    assert instances[0].snapshot_reverted


def test_compiler_route_uses_two_artifacts_and_oracle():
    template, instance, pair, artifact = semantic_fixture()
    template.execution_primitive = "compiler_version_transform"
    config = {
        "name": "compiler_version_transform",
        "source_path": "experiment-data/subjects/MyToken.sol",
        "source_solc": "0.4.11",
        "followup_solc": "0.4.25",
    }
    instance.transformation = config
    pair.transformation = config
    calls = []

    def compiler(path, version):
        calls.append((path, version))
        return CompileResult(
            contract_name="MyToken",
            abi=ABI,
            bytecode=f"6000{version}",
            compiler_version=version,
            success=True,
        )

    result = CanonicalExecutor(
        backend_factory=FakeBackend,
        compiler=compiler,
    ).execute(template, instance, pair, artifact)

    assert result.status == "completed"
    assert result.route == "compiler"
    assert result.verdict == result.oracle_result.verdict
    assert calls == [
        ("experiment-data/subjects/MyToken.sol", "0.4.11"),
        ("experiment-data/subjects/MyToken.sol", "0.4.25"),
    ]


def test_deployment_route_observes_source_and_followup_deployments():
    constructor_abi = [
        {
            "type": "constructor",
            "inputs": [{"name": "_initial", "type": "uint256"}],
        }
    ]
    template = MRTemplate(
        mr_id="MR4.1",
        category="MR4",
        target_operation="contractDeploy",
        execution_primitive="gas_limit_transform",
        required_predicates=("state_change_balance",),
        evidence_sources=("mpsc.registry:MR4.1",),
        status="supported",
    )
    instance = MRInstance(
        instance_id="mytoken.MR4.1.constructor.v01",
        template_id="MR4.1",
        contract_id="mytoken",
        function="constructor",
        parameter_bindings={"_initial": "uint256"},
        source_input={"_initial": 10000},
        transformation={"name": "gas_limit_transform"},
        followup_input={"_initial": 10000},
        observers=("return_value", "transaction.gas_used"),
        predicates=("state_change_balance",),
        predicate_spec={"mu": "mu_f == mu_s", "delta": "delta_f == delta_s"},
        evidence_sources=("mpsc.registry:MR4.1",),
        status="resolved",
    )
    pair = instance.to_test_case_pair()
    pair.source.gas_limit = 3000000
    pair.followup.gas_limit = 3500000
    artifact = CompileResult(
        contract_name="MyToken",
        abi=constructor_abi,
        bytecode="6000",
        success=True,
    )

    result = CanonicalExecutor(backend_factory=FakeBackend).execute(
        template, instance, pair, artifact
    )

    assert result.status == "completed"
    assert result.route == "deployment"
    assert result.source_observation.transaction.submitted
    assert result.followup_observation.transaction.submitted


def test_raw_calldata_route_bypasses_abi_argument_reencoding():
    template, instance, pair, artifact = semantic_fixture()
    template.execution_primitive = "raw_calldata_transform"
    template.mr_id = "MR9.1"
    instance.template_id = "MR9.1"
    instance.instance_id = "mytoken.MR9.1.sendCoin.v01"
    instance.transformation = {"name": "raw_calldata_transform"}
    instance.predicates = ("parameter_swap_raw",)
    pair.template_id = "MR9.1"
    pair.instance_id = instance.instance_id
    pair.transformation = instance.transformation

    result = CanonicalExecutor(backend_factory=FakeBackend).execute(
        template, instance, pair, artifact
    )

    assert result.status == "completed"
    assert result.route == "raw_calldata"
    assert result.source_observation.return_value != (
        result.followup_observation.return_value
    )
