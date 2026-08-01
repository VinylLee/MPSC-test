"""Tests for MR model"""

from mpsc.models import (
    InputRelation,
    KillVector,
    MetamorphicRelation,
    MutableParameter,
    OutputRelation,
    ParameterType,
)
from mpsc.models import (
    TestCase as MPSCTestCase,
)
from mpsc.mr import MRInstance, MRTemplate
from mpsc.mr import TestCasePair as SemanticTestCasePair
from mpsc.mr.instance_catalog import (
    CONTRACT_FUNCTIONS,
    build_all_instances,
    target_counts,
)
from mpsc.mr.registry import MR_BY_ID


def test_mutable_parameter_creation():
    """Test creating a MutableParameter"""
    param = MutableParameter(
        name="to",
        param_type=ParameterType.ADDRESS,
        source="function_argument",
        valid_values=["0x1234", "0x5678"],
        description="Recipient address",
    )

    assert param.name == "to"
    assert param.param_type == ParameterType.ADDRESS
    assert len(param.valid_values) == 2


def test_metamorphic_relation_creation():
    """Test creating a MetamorphicRelation"""
    mr = MetamorphicRelation(
        mr_id="MR1.1",
        category="compiler_version",
        target_operation="contractCompiler",
        preconditions=["version > 0.4.11"],
        input_relation=InputRelation(
            description="Increase compiler version",
            transform="x_f = x_s + Δx",
        ),
        output_relation=OutputRelation(
            description="Outputs should be equal",
            check_type="equal",
        ),
        description="Test compiler version compatibility",
    )

    assert mr.mr_id == "MR1.1"
    assert mr.category == "compiler_version"
    assert mr.output_relation.check_type == "equal"


def test_kill_vector():
    """Test KillVector"""
    kv = KillVector(
        mr_id="MR1.1",
        kills={"mutant_1": True, "mutant_2": False, "mutant_3": True},
    )

    assert kv.mr_id == "MR1.1"
    assert kv.kills["mutant_1"] is True
    assert kv.kills["mutant_2"] is False
    assert len(kv.kills) == 3


def test_registration_adapts_to_canonical_template():
    template = MRTemplate.from_registration(MR_BY_ID["MR6.1"])

    assert template.mr_id == "MR6.1"
    assert template.target_operation == "sendCoin"
    assert template.mutable_parameters == ("amount",)
    assert template.evidence_sources == ("mpsc.registry:MR6.1",)


def test_unproven_instance_is_not_treated_as_resolved():
    instance = MRInstance(
        instance_id="mytoken.MR6.1.sendCoin.v01",
        template_id="MR6.1",
        contract_id="mytoken",
        function="sendCoin",
        status="resolved",
    )

    assert instance.status == "unresolved"
    assert instance.is_semantically_complete is False
    assert "observers" in instance.semantic_gaps()


def test_complete_instance_materializes_test_case_pair():
    instance = MRInstance(
        instance_id="mytoken.MR6.1.sendCoin.v01",
        template_id="MR6.1",
        contract_id="mytoken",
        function="sendCoin",
        parameter_bindings={"to": "address", "amount": "uint256"},
        source_input={"to": "account[1]", "amount": 100},
        transformation={"name": "subtract_from_constant", "constant": 1000},
        followup_input={"to": "account[1]", "amount": 900},
        observers=("return_value", "contract_state.balance"),
        predicates=("return_value_equal", "balance_delta_relation"),
        predicate_spec={"mu": "mu_f == mu_s"},
        evidence_sources=("mpsc.registry:MR6.1",),
        status="resolved",
    )

    pair = instance.to_test_case_pair(seed=7)

    assert instance.is_semantically_complete is True
    assert pair.source.inputs["amount"] == 100
    assert pair.followup.inputs["amount"] == 900
    assert pair.seed == 7
    assert pair.state_strategy == "fresh_deployment"


def test_incomplete_instance_cannot_materialize_pair():
    instance = MRInstance(
        instance_id="rubixi.MR1.1.create.v01",
        template_id="MR1.1",
        contract_id="rubixi",
        function="create",
    )

    try:
        instance.to_test_case_pair()
    except ValueError as error:
        assert "unresolved" in str(error)
    else:
        raise AssertionError("unresolved instance unexpectedly became executable")


def test_contract_level_instance_catalog_reaches_all_target_counts():
    groups = build_all_instances()
    expected_counts = target_counts()
    instances = [instance for group in groups.values() for instance in group]

    assert {contract: len(group) for contract, group in groups.items()} == (
        expected_counts
    )
    assert len(instances) == sum(expected_counts.values()) == 302
    assert len({instance.instance_id for instance in instances}) == 302
    assert {instance.template_id for instance in instances} == set(MR_BY_ID)
    assert all(
        instance.function in CONTRACT_FUNCTIONS[instance.contract_id]
        for instance in instances
    )
    assert all(
        instance.status == "unresolved" and not instance.is_semantically_complete
        for instance in instances
    )


def test_test_case_pair_rejects_implicit_execution_semantics():
    try:
        SemanticTestCasePair(
            instance_id="mytoken.MR6.1.sendCoin.v01",
            template_id="MR6.1",
            function="sendCoin",
            source=MPSCTestCase(inputs={"amount": 100}),
            followup=MPSCTestCase(inputs={"amount": 900}),
            transformation={},
            observers=("return_value",),
            predicate_spec={"mu": "mu_f == mu_s"},
            evidence_sources=("mpsc.registry:MR6.1",),
        )
    except ValueError as error:
        assert "transformation" in str(error)
    else:
        raise AssertionError("pair without a transformation unexpectedly validated")
