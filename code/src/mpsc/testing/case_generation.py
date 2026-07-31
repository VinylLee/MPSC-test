"""Deterministic generation of canonical MyToken metamorphic test pairs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from ..mr.amount_transforms import MR6_TRANSFORMS, TransformContext
from ..mr.semantics import MRInstance, MRTemplate, StateStrategy, TestCasePair


@dataclass
class GeneratedCase:
    """A complete and serializable semantic test unit."""

    template: MRTemplate
    instance: MRInstance
    pair: TestCasePair

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def write_json(self, output_path: str | Path) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                self.to_dict(),
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        return path


def generate_mytoken_mr6_cases(
    accounts: list[str],
    *,
    seed: int = 20260727,
    config_path: str | Path = "code/configs/mrs/mr6.yaml",
    state_strategy: StateStrategy = "fresh_deployment",
) -> list[GeneratedCase]:
    """Build the seven MR6 pairs from audited configuration.

    The implementation recomputes every follow-up amount and rejects a config
    whose recorded value disagrees with the executable transform.
    """

    if len(accounts) < 2:
        raise ValueError("MyToken MR6 generation requires at least two accounts")
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    generated: list[GeneratedCase] = []

    for entry in config["mrs"]:
        mr_id = entry["id"]
        transform = MR6_TRANSFORMS.get(mr_id)
        if transform is None:
            raise ValueError(f"{mr_id} has no executable amount transform")
        source_amount = int(entry["source_amount"])
        result = transform.apply(
            TransformContext(
                source_amount=source_amount,
                sender_balance=int(config["initial_state"]["sender_balance"]),
                receiver_balance=int(config["initial_state"]["receiver_balance"]),
            )
        )
        if not result.valid or result.value is None:
            raise ValueError(f"{mr_id} produced an invalid follow-up: {result.reason}")
        expected_followup = int(entry["followup_amount"])
        if result.value != expected_followup:
            raise ValueError(
                f"{mr_id} transform/config mismatch: "
                f"computed {result.value}, recorded {expected_followup}"
            )

        transform_config = {"name": entry["transform"]["type"]}
        transform_config.update(
            {key: value for key, value in entry["transform"].items() if key != "type"}
        )
        evidence = (f"code/configs/mrs/mr6.yaml:{mr_id}",)
        template = MRTemplate(
            mr_id=mr_id,
            category="MR6",
            target_operation="sendCoin",
            execution_primitive="amount_transform",
            mutable_parameters=("amount",),
            required_predicates=("mr6_amount",),
            description=config["description"],
            evidence_sources=evidence,
            status="supported",
        )
        instance = MRInstance(
            instance_id=f"mytoken.{mr_id}.sendCoin.v01",
            template_id=mr_id,
            contract_id="mytoken",
            function="sendCoin",
            parameter_bindings={"to": "address", "amount": "uint256"},
            source_input={"to": accounts[1], "amount": source_amount},
            transformation=transform_config,
            followup_input={"to": accounts[1], "amount": result.value},
            observers=(
                "return_value",
                "transaction.gas_used",
                "contract_state.token_balances",
            ),
            predicates=("mr6_amount",),
            predicate_spec=dict(entry.get("predicates", {})),
            evidence_sources=evidence,
            status="resolved",
        )
        pair = instance.to_test_case_pair(
            state_strategy=state_strategy,
            seed=seed,
        )
        pair.source.caller = accounts[0]
        pair.followup.caller = accounts[0]
        generated.append(GeneratedCase(template, instance, pair))

    return generated
