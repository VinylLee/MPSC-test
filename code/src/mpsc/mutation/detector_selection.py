"""Detector selection for mutation testing"""

from __future__ import annotations

from ..mr.registry import MR_REGISTRY


def select_eligible_detectors(mr_results: dict[str, str]) -> list[dict]:
    """Select MRs eligible as mutation detectors.

    Criteria:
    - original_contract_verdict == pass
    - implementation_status not in [provisional, unsupported]
    - executable == true

    Args:
      mr_results: dict mapping mr_id -> verdict on original contract

    Returns:
      List of dicts with MR info and eligibility
    """
    eligible = []
    excluded = []

    for mr_reg in MR_REGISTRY:
        mr_id = mr_reg.mr_id
        verdict = mr_results.get(mr_id, "not_run")

        exclusion_reason = None

        if verdict != "pass":
            exclusion_reason = f"Original verdict: {verdict}"
        elif mr_reg.current_status in ("provisional", "unsupported"):
            exclusion_reason = f"Status: {mr_reg.current_status}"
        elif not mr_reg.executable:
            exclusion_reason = "Not executable"

        entry = {
            "mr_id": mr_id,
            "category": mr_reg.category,
            "original_verdict": verdict,
            "eligible": exclusion_reason is None,
            "exclusion_reason": exclusion_reason or "",
        }

        if exclusion_reason:
            excluded.append(entry)
        else:
            eligible.append(entry)

    return eligible + excluded
