

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from ..models import InputRelation, MetamorphicRelation, OutputRelation, TestCase

if TYPE_CHECKING:
    from .registry import MRRegistration


StateStrategy = Literal["fresh_deployment", "snapshot_revert", "shared_state"]


def _require_text(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


@dataclass
class MRTemplate:
    """A contract-independent metamorphic-relation template."""

    mr_id: str
    category: str
    target_operation: str
    execution_primitive: str
    mutable_parameters: tuple[str, ...] = ()
    required_predicates: tuple[str, ...] = ()
    optional_predicates: tuple[str, ...] = ()
    description: str = ""
    evidence_sources: tuple[str, ...] = ()
    status: str = "unsupported"

    def __post_init__(self) -> None:
        _require_text(self.mr_id, "mr_id")
        _require_text(self.category, "category")
        _require_text(self.target_operation, "target_operation")
        _require_text(self.execution_primitive, "execution_primitive")
        self.mutable_parameters = tuple(self.mutable_parameters)
        self.required_predicates = tuple(self.required_predicates)
        self.optional_predicates = tuple(self.optional_predicates)
        self.evidence_sources = tuple(self.evidence_sources)

    @classmethod
    def from_registration(cls, registration: MRRegistration) -> MRTemplate:
        """Adapt the registry without losing provenance."""

        predicates = registration.config.get("required_predicates", ())
        return cls(
            mr_id=registration.mr_id,
            category=registration.category,
            target_operation=registration.source_function,
            execution_primitive=registration.execution_primitive,
            mutable_parameters=tuple(registration.mutable_parameters),
            required_predicates=tuple(predicates),
            evidence_sources=(f"mpsc.registry:{registration.mr_id}",),
            status=registration.current_status,
        )

    def to_legacy_relation(self) -> MetamorphicRelation:
        """Create the legacy relation accepted by the existing oracle."""

        return MetamorphicRelation(
            mr_id=self.mr_id,
            category=self.category,
            target_operation=self.target_operation,
            input_relation=InputRelation(
                description=self.description,
                transform=self.execution_primitive,
            ),
            output_relation=OutputRelation(
                description="; ".join(self.required_predicates),
                check_type="predicate",
                expression=" and ".join(self.required_predicates),
            ),
            description=self.description,
            executable=self.status in {"supported", "provisional"},
        )


@dataclass
class MRInstance:
    """A template bound to one real contract operation.

    Catalog entries may be unresolved. Only entries for which
    :attr:`semantic_gaps` returns an empty tuple are eligible for execution.
    """

    instance_id: str
    template_id: str
    contract_id: str
    function: str
    parameter_bindings: dict[str, Any] = field(default_factory=dict)
    source_input: dict[str, Any] = field(default_factory=dict)
    transformation: dict[str, Any] = field(default_factory=dict)
    followup_input: dict[str, Any] = field(default_factory=dict)
    observers: tuple[str, ...] = ()
    predicates: tuple[str, ...] = ()
    predicate_spec: dict[str, str] = field(default_factory=dict)
    evidence_sources: tuple[str, ...] = ()
    status: str = "unresolved"

    def __post_init__(self) -> None:
        _require_text(self.instance_id, "instance_id")
        _require_text(self.template_id, "template_id")
        _require_text(self.contract_id, "contract_id")
        _require_text(self.function, "function")
        self.observers = tuple(self.observers)
        self.predicates = tuple(self.predicates)
        self.evidence_sources = tuple(self.evidence_sources)
        if self.status in {"registered", "resolved"} and self.semantic_gaps():
            self.status = "unresolved"

    def semantic_gaps(self) -> tuple[str, ...]:
        """Return missing data needed before this instance can execute."""

        gaps: list[str] = []
        if not self.parameter_bindings:
            gaps.append("parameter_bindings")
        if not self.transformation:
            gaps.append("transformation")
        if not self.observers:
            gaps.append("observers")
        if not self.predicates:
            gaps.append("predicates")
        if not self.predicate_spec:
            gaps.append("predicate_spec")
        if not self.evidence_sources:
            gaps.append("evidence_sources")
        return tuple(gaps)

    @property
    def is_semantically_complete(self) -> bool:
        return not self.semantic_gaps()

    def to_test_case_pair(
        self,
        *,
        state_strategy: StateStrategy = "fresh_deployment",
        seed: int | None = None,
    ) -> TestCasePair:
        """Materialize an executable pair, refusing count-only entries."""

        gaps = self.semantic_gaps()
        if gaps:
            raise ValueError(
                f"{self.instance_id} is unresolved; missing: {', '.join(gaps)}"
            )
        return TestCasePair(
            instance_id=self.instance_id,
            template_id=self.template_id,
            function=self.function,
            source=TestCase(inputs=dict(self.source_input)),
            followup=TestCase(inputs=dict(self.followup_input)),
            transformation=dict(self.transformation),
            observers=self.observers,
            predicate_spec=dict(self.predicate_spec),
            evidence_sources=self.evidence_sources,
            state_strategy=state_strategy,
            seed=seed,
        )

    def validate_binding(self, abi: list[dict[str, Any]]):
        """Validate this instance against an ABI using the canonical validator."""

        from .binding import validate_binding

        return validate_binding(self, abi)


@dataclass
class TestCasePair:
    """Concrete source/follow-up tests plus their execution semantics."""

    instance_id: str
    template_id: str
    function: str
    source: TestCase
    followup: TestCase
    transformation: dict[str, Any]
    observers: tuple[str, ...]
    predicate_spec: dict[str, str]
    evidence_sources: tuple[str, ...]
    state_strategy: StateStrategy = "fresh_deployment"
    seed: int | None = None

    def __post_init__(self) -> None:
        _require_text(self.instance_id, "instance_id")
        _require_text(self.template_id, "template_id")
        _require_text(self.function, "function")
        if self.state_strategy not in {
            "fresh_deployment",
            "snapshot_revert",
            "shared_state",
        }:
            raise ValueError(f"unsupported state strategy: {self.state_strategy}")
        if not self.transformation:
            raise ValueError(
                "transformation must describe the source-to-follow-up change"
            )
        self.observers = tuple(self.observers)
        self.evidence_sources = tuple(self.evidence_sources)
        if not self.observers:
            raise ValueError("at least one observer is required")
        if not self.predicate_spec:
            raise ValueError("at least one predicate is required")
        if not self.evidence_sources:
            raise ValueError("at least one evidence source is required")
