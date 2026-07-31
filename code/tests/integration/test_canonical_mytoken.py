"""Real local-chain integration test for the canonical MyToken path."""

from mpsc.chain.local_backend import LocalChainBackend
from mpsc.mr import MRInstance, MRTemplate
from mpsc.solidity.compiler import compile_contract_solcx
from mpsc.testing.canonical_executor import CanonicalExecutor


def test_mr6_1_executes_on_two_fresh_local_chains():
    artifact = compile_contract_solcx("experiment-data/subjects/MyToken.sol", "0.4.11")
    assert artifact.success, artifact.errors
    accounts = LocalChainBackend().get_accounts()
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
        parameter_bindings={"to": "address", "amount": "uint256"},
        source_input={"to": accounts[1], "amount": 100},
        transformation={"name": "subtract_from_constant", "constant": 1000},
        followup_input={"to": accounts[1], "amount": 900},
        observers=("return_value", "contract_state.token_balances"),
        predicates=("mr6_amount",),
        predicate_spec={"mu": "mu_f == mu_s"},
        evidence_sources=("mpsc.registry:MR6.1",),
        status="resolved",
    )
    pair = instance.to_test_case_pair(seed=1)
    pair.source.caller = accounts[0]
    pair.followup.caller = accounts[0]

    result = CanonicalExecutor().execute(template, instance, pair, artifact)

    assert result.status == "completed", result.errors
    assert result.binding is not None and result.binding.valid
    assert result.source_observation.transaction.submitted
    assert result.followup_observation.transaction.submitted
    assert result.oracle_result is not None
    assert result.verdict == result.oracle_result.verdict
