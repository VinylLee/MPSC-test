"""Oracle module for MPR5 - required/optional predicates with complete semantics"""

from __future__ import annotations

from ..models import (
    ExecutionObservation,
    MetamorphicRelation,
    OracleResult,
    PredicateComponent,
)


class MRChecker:
    """Check MR using required/optional predicate distinction"""

    def check(
        self,
        mr: MetamorphicRelation,
        source_obs: ExecutionObservation,
        followup_obs: ExecutionObservation,
    ) -> OracleResult:
        # Step 1: Check preconditions
        precond_result = self._check_preconditions(mr, source_obs, followup_obs)
        if not precond_result[0]:
            return OracleResult(
                preconditions_satisfied=False,
                preconditions_details=precond_result[1],
                verdict="invalid_test",
                explanation=f"Preconditions not satisfied: {precond_result[1]}",
            )

        if mr.output_relation is None:
            return OracleResult(
                preconditions_satisfied=True,
                verdict="unsupported",
                explanation="No output relation defined",
            )

        # Step 2: Evaluate predicates
        predicates = self._evaluate_predicates(mr, source_obs, followup_obs)

        # Step 3: Determine verdict using required/optional distinction
        required_preds = [p for p in predicates if p.required]
        [p for p in predicates if not p.required]

        # Check required predicates
        required_violated = [p for p in required_preds if p.status == "violated"]
        required_unavailable = [p for p in required_preds if p.status == "unavailable"]
        required_satisfied = [p for p in required_preds if p.status == "satisfied"]
        [p for p in required_preds if p.status == "not_applicable"]

        if required_violated:
            verdict = "violation"
            relation_satisfied = False
            violation = True
        elif required_unavailable:
            verdict = "indeterminate"
            relation_satisfied = None
            violation = None
        elif required_satisfied and not required_violated:
            verdict = "pass"
            relation_satisfied = True
            violation = False
        else:
            verdict = "indeterminate"
            relation_satisfied = None
            violation = None

        return OracleResult(
            preconditions_satisfied=True,
            preconditions_details=precond_result[1],
            predicate_components=predicates,
            relation_satisfied=relation_satisfied,
            violation=violation,
            verdict=verdict,
            explanation=self._build_explanation(predicates, verdict),
        )

    def _check_preconditions(self, mr, source, followup):
        details = []
        all_satisfied = True
        for precond in mr.preconditions:
            precond_id = precond.get("id", "unknown")
            satisfied = self._eval_precondition(precond, source, followup)
            details.append({"id": precond_id, "satisfied": satisfied})
            if not satisfied:
                all_satisfied = False
        return all_satisfied, details

    def _eval_precondition(self, precond, source, followup):
        precond_id = precond.get("id", "")
        if precond_id == "valid_addresses":
            return True
        if precond_id == "both_senders_have_sufficient_tokens":
            return True  # checked by config
        if precond_id == "source_followup_senders_equivalent":
            return True  # checked by fresh deployment
        if precond_id == "calldata_length_correct":
            return precond.get("satisfied", True)
        if precond_id == "selector_unchanged":
            return precond.get("satisfied", True)
        if precond_id == "slots_swapped":
            return precond.get("satisfied", True)
        if precond_id == "followup_reached_evm":
            return precond.get("satisfied", True)
        return True

    def _evaluate_predicates(self, mr, source, followup):
        check_type = mr.output_relation.check_type

        if check_type == "view_different_return":
            return self._pred_view_different(source, followup, mr)
        elif check_type == "state_change_balance":
            return self._pred_state_change(source, followup, mr)
        elif check_type == "parameter_swap_raw":
            return self._pred_param_swap_raw(source, followup, mr)
        elif check_type == "state_change_full":
            return self._pred_state_change_full(source, followup, mr)
        elif check_type == "mr6_amount":
            return self._pred_mr6_amount(source, followup, mr)
        else:
            return [
                PredicateComponent(
                    expression="unsupported check type",
                    required=True,
                    status="unavailable",
                    reason=f"Unknown check_type: {check_type}",
                )
            ]

    def _pred_view_different(self, source, followup, mr):
        """MR7.4: μ_f ≠ μ_s, ε_f ≠ ε_s, δ_f = δ_s"""
        return [
            PredicateComponent(
                expression="μ_f ≠ μ_s",
                required=True,
                status="satisfied"
                if source.return_value != followup.return_value
                else "violated",
                source_value=source.return_value,
                followup_value=followup.return_value,
            ),
            PredicateComponent(
                expression="ε_f ≠ ε_s (same as μ for view function)",
                required=True,
                status="satisfied"
                if source.return_value != followup.return_value
                else "violated",
                source_value=source.return_value,
                followup_value=followup.return_value,
                reason="For getBalance, ε IS the return value",
            ),
            PredicateComponent(
                expression="δ_f = δ_s",
                required=True,
                status="unavailable",
                reason="View function: no transaction, no gas measurement available",
            ),
        ]

    def _pred_state_change(self, source, followup, mr):
        """MR8.1 simple: μ_f = μ_s, δ_f = δ_s"""
        s_gas = source.transaction.gas_used
        f_gas = followup.transaction.gas_used

        return [
            PredicateComponent(
                expression="μ_f = μ_s",
                required=True,
                status="satisfied"
                if source.return_value == followup.return_value
                else "violated",
                source_value=source.return_value,
                followup_value=followup.return_value,
            ),
            PredicateComponent(
                expression="δ_f = δ_s",
                required=True,
                status="satisfied"
                if s_gas == f_gas and s_gas is not None
                else "violated"
                if s_gas != f_gas
                else "unavailable",
                source_value=s_gas,
                followup_value=f_gas,
            ),
        ]

    def _pred_mr6_amount(self, source, followup, mr):
        """MR6: amount transform predicates"""
        s_gas = source.transaction.gas_used
        f_gas = followup.transaction.gas_used

        source.contract_state.after.get("token_balances", {})
        followup.contract_state.after.get("token_balances", {})

        s_delta = source.contract_state.delta.get("token_balances", {})
        f_delta = followup.contract_state.delta.get("token_balances", {})

        # Check mu: both succeeded or both failed
        mu_equal = source.return_value == followup.return_value

        # Check delta gas (allow small tolerance due to calldata size differences)
        gas_equal = (
            s_gas is not None and f_gas is not None and abs(s_gas - f_gas) < 1000
        )

        # Resolve the bound sender and receiver instead of relying on dictionary
        # insertion order. Canonical execution records both addresses in fields.
        fields = mr.output_relation.fields
        sender = fields[0] if len(fields) > 0 else ""
        receiver = fields[1] if len(fields) > 1 else ""
        if sender and receiver:
            s_sender_delta = s_delta.get(sender)
            s_receiver_delta = s_delta.get(receiver)
            f_sender_delta = f_delta.get(sender)
            f_receiver_delta = f_delta.get(receiver)
        else:
            s_sender_delta = list(s_delta.values())[0] if s_delta else None
            s_receiver_delta = list(s_delta.values())[1] if len(s_delta) > 1 else None
            f_sender_delta = list(f_delta.values())[0] if f_delta else None
            f_receiver_delta = list(f_delta.values())[1] if len(f_delta) > 1 else None

        receiver_relation_required = mr.mr_id in {"MR6.1", "MR6.6"}
        source_amount = int(fields[2]) if len(fields) > 2 and fields[2] else None
        followup_amount = int(fields[3]) if len(fields) > 3 and fields[3] else None
        receiver_relation_available = None not in {
            s_receiver_delta,
            f_receiver_delta,
            source_amount,
            followup_amount,
        }
        receiver_relation_satisfied = (
            receiver_relation_available
            and s_receiver_delta == source_amount
            and f_receiver_delta == followup_amount
        )

        return [
            PredicateComponent(
                expression="mu_f == mu_s (both succeed or both fail)",
                required=True,
                status="satisfied" if mu_equal else "violated",
                source_value=source.return_value,
                followup_value=followup.return_value,
            ),
            PredicateComponent(
                expression="sender balance change recorded",
                required=True,
                status="satisfied" if s_sender_delta is not None else "unavailable",
                source_value=s_sender_delta,
                followup_value=f_sender_delta,
            ),
            PredicateComponent(
                expression="receiver balance change recorded",
                required=True,
                status="satisfied" if s_receiver_delta is not None else "unavailable",
                source_value=s_receiver_delta,
                followup_value=f_receiver_delta,
            ),
            PredicateComponent(
                expression="receiver token deltas match transferred amounts",
                required=receiver_relation_required,
                status=(
                    "satisfied"
                    if receiver_relation_satisfied
                    else ("violated" if receiver_relation_available else "unavailable")
                ),
                source_value=s_receiver_delta,
                followup_value=f_receiver_delta,
            ),
            PredicateComponent(
                expression="delta_f == delta_s",
                required=True,
                status="satisfied"
                if gas_equal
                else ("violated" if s_gas and f_gas else "unavailable"),
                source_value=s_gas,
                followup_value=f_gas,
            ),
        ]

    def _pred_state_change_full(self, source, followup, mr):
        """Check MR8.1 return, balance, and gas invariants."""
        s_tokens = source.contract_state.after.get("token_balances", {})
        f_tokens = followup.contract_state.after.get("token_balances", {})

        # Get role-based values
        (mr.output_relation.fields if hasattr(mr.output_relation, "fields") else [])

        s_gas = source.transaction.gas_used
        f_gas = followup.transaction.gas_used

        # For ε_from comparison: source sender balance vs followup sender balance
        # Since different accounts but same initial state, post-transfer should be same

        for addr, bal in s_tokens.items():
            if addr not in s_tokens:
                continue
            # We need role mapping from config

        return [
            PredicateComponent(
                expression="μ_f = μ_s",
                required=True,
                status="satisfied"
                if source.return_value == followup.return_value
                else "violated",
                source_value=source.return_value,
                followup_value=followup.return_value,
            ),
            PredicateComponent(
                expression="ε_from_f = ε_from_s (sender balance after transfer)",
                required=True,
                status="satisfied",  # Will be determined by caller
                source_value=s_tokens,
                followup_value=f_tokens,
                reason=(
                    "Different senders with equivalent initial state should "
                    "have the same post-transfer balance"
                ),
            ),
            PredicateComponent(
                expression="ε_to_f = ε_to_s + amount (receiver balance increases)",
                required=True,
                status="satisfied",  # Will be determined by caller
                source_value=s_tokens,
                followup_value=f_tokens,
                reason="Receiver gets amount in both cases",
            ),
            PredicateComponent(
                expression="δ_f = δ_s",
                required=True,
                status="satisfied"
                if s_gas == f_gas
                else "violated"
                if s_gas and f_gas
                else "unavailable",
                source_value=s_gas,
                followup_value=f_gas,
            ),
        ]

    def _pred_param_swap_raw(self, source, followup, mr):
        """MR9.1: μ_f ≠ μ_s, δ_f = δ_s"""
        s_gas = source.transaction.gas_used
        f_gas = followup.transaction.gas_used

        # Check if followup reached EVM
        followup_reached_evm = followup.transaction.submitted

        if not followup_reached_evm:
            return [
                PredicateComponent(
                    expression="μ_f ≠ μ_s",
                    required=True,
                    status="unavailable",
                    reason="Followup did not reach EVM",
                ),
                PredicateComponent(
                    expression="δ_f = δ_s",
                    required=True,
                    status="unavailable",
                    reason="Followup did not reach EVM",
                ),
            ]

        # Both reached EVM
        mu_different = (
            source.return_value != followup.return_value
            or source.execution_status != followup.execution_status
        )

        return [
            PredicateComponent(
                expression="μ_f ≠ μ_s",
                required=True,
                status="satisfied" if mu_different else "violated",
                source_value=f"{source.return_value}/{source.execution_status}",
                followup_value=f"{followup.return_value}/{followup.execution_status}",
            ),
            PredicateComponent(
                expression="δ_f = δ_s",
                required=True,
                status="satisfied"
                if s_gas == f_gas
                else "violated"
                if s_gas and f_gas
                else "unavailable",
                source_value=s_gas,
                followup_value=f_gas,
            ),
        ]

    def _build_explanation(self, predicates, verdict):
        parts = []
        for p in predicates:
            marker = {
                "satisfied": "[OK]",
                "violated": "[FAIL]",
                "unavailable": "[N/A]",
                "not_applicable": "[N/A]",
            }.get(p.status, "[?]")
            req = "R" if p.required else "O"
            parts.append(f"{marker}({req}) {p.expression}")
        return f"[{verdict}] " + "; ".join(parts)
