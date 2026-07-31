"""Canonical, semantics-aware execution path for metamorphic tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from ..chain.calldata import build_calldata, swap_abi_slots
from ..chain.local_backend import LocalChainBackend
from ..models import (
    ContractState,
    ExecutionObservation,
    InputRelation,
    MetamorphicRelation,
    OracleResult,
    OutputRelation,
    TestCase,
    TransactionInfo,
)
from ..mr.binding import BindingIssue, BindingValidationResult, validate_binding
from ..mr.semantics import MRInstance, MRTemplate, TestCasePair
from ..solidity.compiler import CompileResult, compile_contract_solcx
from .oracle import MRChecker

CALL_ROUTES = frozenset(
    {
        "amount_transform",
        "recipient_transform",
        "query_address_transform",
        "address_role_transform",
    }
)

SPECIALIZED_ROUTES = {
    "compiler_version_transform": "compiler",
    "caller_transform": "deployment",
    "gas_limit_transform": "deployment",
    "raw_calldata_transform": "raw_calldata",
    "deployment_env_transform": "deployment_environment",
}


@dataclass
class CanonicalExecutionResult:
    """One MR execution with test verdicts sourced only from the Oracle."""

    status: Literal["completed", "invalid_binding", "unsupported", "execution_error"]
    instance_id: str
    template_id: str
    route: str
    binding: BindingValidationResult | None = None
    source_observation: ExecutionObservation | None = None
    followup_observation: ExecutionObservation | None = None
    oracle_result: OracleResult | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> str | None:
        """Return the Oracle verdict; infrastructure statuses are not verdicts."""

        return self.oracle_result.verdict if self.oracle_result is not None else None


class CanonicalExecutor:
    """Execute a validated source/follow-up pair through one controlled path."""

    def __init__(
        self,
        backend_factory: Callable[[], LocalChainBackend] = LocalChainBackend,
        checker: MRChecker | None = None,
        compiler: Callable[[str, str | None], CompileResult] = compile_contract_solcx,
    ) -> None:
        self.backend_factory = backend_factory
        self.checker = checker or MRChecker()
        self.compiler = compiler

    def execute(
        self,
        template: MRTemplate,
        instance: MRInstance,
        pair: TestCasePair,
        artifact: CompileResult,
    ) -> CanonicalExecutionResult:
        route = self._route_for(template.execution_primitive)
        identity_issues = self._validate_identity(template, instance, pair)
        if identity_issues:
            binding = BindingValidationResult("invalid_binding", identity_issues)
            return CanonicalExecutionResult(
                status="invalid_binding",
                instance_id=instance.instance_id,
                template_id=template.mr_id,
                route=route,
                binding=binding,
                errors=[issue.message for issue in identity_issues],
            )

        if route in {"unknown", "deployment_environment"}:
            return CanonicalExecutionResult(
                status="unsupported",
                instance_id=instance.instance_id,
                template_id=template.mr_id,
                route=route,
                errors=[f"canonical {route} execution is not supported"],
            )

        source_artifact = artifact
        followup_artifact = artifact
        if route == "compiler":
            compile_config = pair.transformation
            required = {"source_path", "source_solc", "followup_solc"}
            missing = sorted(required - set(compile_config))
            if missing:
                return CanonicalExecutionResult(
                    status="invalid_binding",
                    instance_id=instance.instance_id,
                    template_id=template.mr_id,
                    route=route,
                    errors=[f"compiler route missing: {', '.join(missing)}"],
                )
            source_artifact = self.compiler(
                compile_config["source_path"], compile_config["source_solc"]
            )
            followup_artifact = self.compiler(
                compile_config["source_path"], compile_config["followup_solc"]
            )

        binding = validate_binding(instance, source_artifact.abi)
        if not binding.valid:
            return CanonicalExecutionResult(
                status=binding.status,
                instance_id=instance.instance_id,
                template_id=template.mr_id,
                route=route,
                binding=binding,
                errors=[issue.message for issue in binding.issues],
            )

        if route == "compiler":
            followup_binding = validate_binding(instance, followup_artifact.abi)
            if not followup_binding.valid:
                return CanonicalExecutionResult(
                    status=followup_binding.status,
                    instance_id=instance.instance_id,
                    template_id=template.mr_id,
                    route=route,
                    binding=followup_binding,
                    errors=[issue.message for issue in followup_binding.issues],
                )

        if any(
            not candidate.success or not candidate.bytecode
            for candidate in (source_artifact, followup_artifact)
        ):
            return CanonicalExecutionResult(
                status="invalid_binding",
                instance_id=instance.instance_id,
                template_id=template.mr_id,
                route=route,
                binding=binding,
                errors=["compiled artifact is unsuccessful or has empty bytecode"],
            )

        try:
            if route == "contract_call":
                source, followup = self._execute_pair(pair, artifact)
            elif route == "compiler":
                source, followup = self._execute_fresh_with_artifacts(
                    pair, source_artifact, followup_artifact
                )
            elif route == "deployment":
                source, followup = self._execute_deployment_pair(pair, artifact)
            elif route == "raw_calldata":
                source, followup = self._execute_raw_pair(pair, artifact)
            else:
                raise RuntimeError(f"unhandled route: {route}")
            relation = self._build_relation(template, instance, pair)
            oracle = self.checker.check(relation, source, followup)
            return CanonicalExecutionResult(
                status="completed",
                instance_id=instance.instance_id,
                template_id=template.mr_id,
                route=route,
                binding=binding,
                source_observation=source,
                followup_observation=followup,
                oracle_result=oracle,
            )
        except Exception as error:
            return CanonicalExecutionResult(
                status="execution_error",
                instance_id=instance.instance_id,
                template_id=template.mr_id,
                route=route,
                binding=binding,
                errors=[f"{type(error).__name__}: {error}"],
            )

    def _execute_pair(
        self, pair: TestCasePair, artifact: CompileResult
    ) -> tuple[ExecutionObservation, ExecutionObservation]:
        if pair.state_strategy == "fresh_deployment":
            source_backend = self.backend_factory()
            followup_backend = self.backend_factory()
            source_address = self._deploy(source_backend, artifact)
            followup_address = self._deploy(followup_backend, artifact)
            source = self._execute_case(
                source_backend, source_address, artifact, pair, pair.source
            )
            followup = self._execute_case(
                followup_backend, followup_address, artifact, pair, pair.followup
            )
            return source, followup

        backend = self.backend_factory()
        address = self._deploy(backend, artifact)
        if pair.state_strategy == "snapshot_revert":
            snapshot_id = backend.take_snapshot()
            source = self._execute_case(backend, address, artifact, pair, pair.source)
            backend.revert_to_snapshot(snapshot_id)
            followup = self._execute_case(
                backend, address, artifact, pair, pair.followup
            )
            return source, followup

        source = self._execute_case(backend, address, artifact, pair, pair.source)
        followup = self._execute_case(backend, address, artifact, pair, pair.followup)
        return source, followup

    def _execute_fresh_with_artifacts(
        self,
        pair: TestCasePair,
        source_artifact: CompileResult,
        followup_artifact: CompileResult,
    ) -> tuple[ExecutionObservation, ExecutionObservation]:
        source_backend = self.backend_factory()
        followup_backend = self.backend_factory()
        source_address = self._deploy(source_backend, source_artifact)
        followup_address = self._deploy(followup_backend, followup_artifact)
        return (
            self._execute_case(
                source_backend,
                source_address,
                source_artifact,
                pair,
                pair.source,
            ),
            self._execute_case(
                followup_backend,
                followup_address,
                followup_artifact,
                pair,
                pair.followup,
            ),
        )

    def _execute_deployment_pair(
        self, pair: TestCasePair, artifact: CompileResult
    ) -> tuple[ExecutionObservation, ExecutionObservation]:
        return (
            self._observe_deployment(self.backend_factory(), artifact, pair.source),
            self._observe_deployment(self.backend_factory(), artifact, pair.followup),
        )

    @staticmethod
    def _observe_deployment(
        backend, artifact: CompileResult, case: TestCase
    ) -> ExecutionObservation:
        constructor = next(
            (entry for entry in artifact.abi if entry.get("type") == "constructor"),
            {"inputs": []},
        )
        args = [case.inputs[item["name"]] for item in constructor.get("inputs", [])]
        accounts = backend.get_accounts()
        receipt = backend.deploy(
            bytecode=artifact.bytecode,
            abi=artifact.abi,
            args=args,
            sender=case.caller or accounts[0],
            value=case.value,
            gas_limit=case.gas_limit,
        )
        return ExecutionObservation(
            outcome_type=(
                "success_transaction" if receipt.success else "deployment_error"
            ),
            execution_status="success" if receipt.success else "deployment_error",
            return_value=receipt.success,
            transaction=TransactionInfo(
                submitted=True,
                hash=receipt.tx_hash,
                receipt_status=1 if receipt.success else 0,
                gas_used=receipt.gas_used,
            ),
            contract_state=ContractState(
                after={"contract_address": receipt.contract_address}
            ),
        )

    def _execute_raw_pair(
        self, pair: TestCasePair, artifact: CompileResult
    ) -> tuple[ExecutionObservation, ExecutionObservation]:
        function_abi = next(
            entry
            for entry in artifact.abi
            if entry.get("type") == "function" and entry.get("name") == pair.function
        )
        inputs = function_abi.get("inputs", [])
        signature = (
            f"{pair.function}(" + ",".join(item["type"] for item in inputs) + ")"
        )
        source_calldata = build_calldata(
            signature,
            [(item["type"], pair.source.inputs[item["name"]]) for item in inputs],
        )
        followup_calldata = build_calldata(
            signature,
            [(item["type"], pair.followup.inputs[item["name"]]) for item in inputs],
        )
        transform_name = pair.transformation.get("name") or pair.transformation.get(
            "type"
        )
        if transform_name in {"raw_calldata_transform", "swap_abi_slots"}:
            followup_calldata = swap_abi_slots(followup_calldata)
        else:
            raise ValueError(f"unsupported raw calldata transform: {transform_name}")

        source_backend = self.backend_factory()
        followup_backend = self.backend_factory()
        source_address = self._deploy(source_backend, artifact)
        followup_address = self._deploy(followup_backend, artifact)
        source_accounts = source_backend.get_accounts()
        followup_accounts = followup_backend.get_accounts()
        return (
            source_backend.execute_raw_and_observe(
                contract_address=source_address,
                abi=artifact.abi,
                calldata=source_calldata,
                sender=pair.source.caller or source_accounts[0],
                accounts_to_track=source_accounts,
            ),
            followup_backend.execute_raw_and_observe(
                contract_address=followup_address,
                abi=artifact.abi,
                calldata=followup_calldata,
                sender=pair.followup.caller or followup_accounts[0],
                accounts_to_track=followup_accounts,
            ),
        )

    @staticmethod
    def _build_relation(
        template: MRTemplate, instance: MRInstance, pair: TestCasePair
    ) -> MetamorphicRelation:
        return MetamorphicRelation(
            mr_id=template.mr_id,
            category=template.category,
            target_operation=instance.function,
            input_relation=InputRelation(
                description=template.description,
                transform=str(pair.transformation),
            ),
            output_relation=OutputRelation(
                description="; ".join(instance.predicates),
                check_type=instance.predicates[0],
                fields=[
                    pair.source.caller or "",
                    str(instance.source_input.get("to", "")),
                    str(instance.source_input.get("amount", "")),
                    str(instance.followup_input.get("amount", "")),
                ],
            ),
            description=template.description,
        )

    @staticmethod
    def _deploy(backend, artifact: CompileResult) -> str:
        accounts = backend.get_accounts()
        receipt = backend.deploy(
            bytecode=artifact.bytecode,
            abi=artifact.abi,
            sender=accounts[0],
        )
        if not receipt.success or not receipt.contract_address:
            raise RuntimeError("contract deployment failed")
        return receipt.contract_address

    @staticmethod
    def _execute_case(
        backend,
        contract_address: str,
        artifact: CompileResult,
        pair: TestCasePair,
        case: TestCase,
    ) -> ExecutionObservation:
        function_abi = next(
            entry
            for entry in artifact.abi
            if entry.get("type") == "function" and entry.get("name") == pair.function
        )
        args = [case.inputs[item["name"]] for item in function_abi.get("inputs", [])]
        accounts = backend.get_accounts()
        sender = case.caller or accounts[0]
        is_view = function_abi.get("stateMutability") in {"view", "pure"} or bool(
            function_abi.get("constant")
        )
        return backend.execute_and_observe(
            contract_address=contract_address,
            abi=artifact.abi,
            function_name=pair.function,
            args=args,
            sender=sender,
            value=case.value,
            gas_limit=case.gas_limit,
            accounts_to_track=accounts,
            is_view=is_view,
        )

    @staticmethod
    def _route_for(primitive: str) -> str:
        if primitive in CALL_ROUTES:
            return "contract_call"
        return SPECIALIZED_ROUTES.get(primitive, "unknown")

    @staticmethod
    def _validate_identity(
        template: MRTemplate, instance: MRInstance, pair: TestCasePair
    ) -> list[BindingIssue]:
        issues: list[BindingIssue] = []
        comparisons = (
            ("template_id", template.mr_id, instance.template_id),
            ("pair.template_id", template.mr_id, pair.template_id),
            ("pair.instance_id", instance.instance_id, pair.instance_id),
            ("pair.function", instance.function, pair.function),
            ("pair.source", instance.source_input, pair.source.inputs),
            ("pair.followup", instance.followup_input, pair.followup.inputs),
            ("pair.transformation", instance.transformation, pair.transformation),
            ("pair.predicate_spec", instance.predicate_spec, pair.predicate_spec),
        )
        for field_name, expected, actual in comparisons:
            if expected != actual:
                issues.append(
                    BindingIssue(
                        "semantic_identity_mismatch",
                        field_name,
                        f"{field_name} mismatch: expected {expected!r}, got {actual!r}",
                    )
                )
        return issues
