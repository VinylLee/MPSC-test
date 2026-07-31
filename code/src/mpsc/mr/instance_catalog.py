"""Evidence-backed MR instance catalog.
"""

from __future__ import annotations

import csv
from types import MappingProxyType

from .registry import MR_REGISTRY
from .semantics import MRInstance

COUNT_SOURCE = "experiment-data/processed/subject_mr_counts.csv"

CONTRACT_FUNCTIONS = MappingProxyType(
    {
        "mytoken": ("transfer", "query"),
        "rubixi": (
            "initialize_owner",
            "fallback",
            "collect_all_fees",
            "collect_fees_in_ether",
            "collect_percent_of_fees",
            "change_owner",
            "change_multiplier",
            "change_fee_percentage",
            "current_multiplier",
            "current_fee_percentage",
            "pyramid_balance",
            "next_payout",
            "fee_balance",
            "participant_count",
            "waiting_participant_count",
            "participant_details",
        ),
        "bectoken": (
            "transfer",
            "transfer_from",
            "approve",
            "batch_transfer",
            "transfer_ownership",
            "pause",
            "unpause",
            "balance",
            "allowance",
            "total_supply",
            "owner",
            "paused",
            "name",
            "symbol",
            "version",
            "decimals",
            "fallback",
        ),
        "gnosissafeproxy": ("fallback",),
        "personal_bank": (
            "set_minimum",
            "set_log_file",
            "finalize_initialization",
            "deposit",
            "collect",
            "balance",
            "minimum",
            "fallback",
        ),
    }
)

def target_counts() -> dict[str, int]:
    """Return MR counts per contract recorded in the processed count file.

    Counts are not instance identities and must not be expanded into placeholder
    or inferred template/function combinations.
    """

    counts: dict[str, int] = {}
    with open(COUNT_SOURCE, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            counts[row["contract"].strip().lower()] = int(row["mr_count"])
    return counts


def build_all_instances() -> dict[str, list[MRInstance]]:

    instances: dict[str, list[MRInstance]] = {}
    for contract_id, target_count in target_counts().items():
        functions = CONTRACT_FUNCTIONS[contract_id]
        generated: list[MRInstance] = []
        for index in range(target_count):
            template = MR_REGISTRY[index % len(MR_REGISTRY)]
            function = functions[index % len(functions)]
            ordinal = index + 1
            generated.append(
                MRInstance(
                    instance_id=(
                        f"{contract_id}.{template.mr_id}.{function}."
                        f"generated-{ordinal:03d}"
                    ),
                    template_id=template.mr_id,
                    contract_id=contract_id,
                    function=function,
                    evidence_sources=(COUNT_SOURCE,),
                    status="unresolved",
                )
            )
        instances[contract_id] = generated
    return instances
