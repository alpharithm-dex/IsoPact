from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from isopact.domain.canonical import canonicalize
from isopact.domain.models import (
    AuthorizationDecision,
    Decision,
    ExecutionOutcome,
    Money,
    OperationIntent,
    ReasonCode,
    ReservationState,
)
from isopact.reservations.engine import ReservationEngine
from isopact.simulator.models import InterceptionDecision, ScheduledAction

from .activation import ActiveOutcomePact


@dataclass(frozen=True, slots=True)
class NormalizedGatewayOperation:
    resolution_path: str
    event_type: str
    amount: Money | None
    resource: str | None


class IsoPactGatewayInterceptor:
    """Deterministic Stage 4 safety kernel; it has no model/provider dependency."""

    def __init__(self, active_pact: ActiveOutcomePact, repository: Any) -> None:
        self.active_pact = active_pact
        self.repository = repository
        self.engine = ReservationEngine(repository)
        self._pending: dict[str, tuple[AuthorizationDecision, InterceptionDecision]] = {}
        self.model_calls = 0

    def _normalize(self, action: ScheduledAction) -> NormalizedGatewayOperation | None:
        values = action.inputs
        operation = (action.target_system.lower(), action.tool.lower())
        if operation == ("stripe", "create_refund"):
            return NormalizedGatewayOperation(
                "successful_refund",
                "refund",
                Money(str(values["currency"]), int(values["amount_minor_units"])),
                None,
            )
        if operation == ("carrier", "create_label"):
            return NormalizedGatewayOperation(
                "confirmed_replacement",
                "replacement",
                None,
                f"replacement:{self.active_pact.order_id}",
            )
        if operation == ("warehouse", "reserve_stock"):
            return NormalizedGatewayOperation(
                "confirmed_replacement",
                "replacement_stock",
                None,
                f"replacement:{self.active_pact.order_id}:{values['resource']}",
            )
        if operation == ("crm", "issue_credit"):
            return NormalizedGatewayOperation(
                "authorized_goodwill",
                "goodwill_credit",
                Money(str(values["currency"]), int(values["amount_minor_units"])),
                None,
            )
        return None

    def _audit(
        self,
        action: ScheduledAction,
        decision: str,
        reason: str,
        *,
        operation_identity: str | None = None,
        slot: str | None = None,
        before: str | None = None,
        after: str | None = None,
    ) -> InterceptionDecision:
        policy = self.active_pact.pact.policy
        return InterceptionDecision(
            decision=decision,
            reason_code=reason,
            pact_id=self.active_pact.pact.pact_id,
            actor=action.actor,
            action_id=action.action_id,
            target_system=action.target_system.lower(),
            tool=action.tool.lower(),
            operation_identity=operation_identity or "NOT_APPLICABLE_STAGE4",
            resolution_slot=slot,
            policy_id=policy.policy_id,
            policy_version=policy.version,
            reservation_state_before=before,
            external_call_executed=False,
            reservation_state_after=after,
            trace_id=f"trace-{action.action_id}",
        )

    def intercept(self, action: ScheduledAction) -> InterceptionDecision:
        normalized = self._normalize(action)
        if normalized is None or not action.enforcement_boundary:
            return self._audit(action, "ALLOW", "OUTSIDE_STAGE4_SAFETY_KERNEL")
        if normalized.resolution_path not in self.active_pact.pact.allowed_resolution_paths:
            return self._audit(action, "BLOCK", "RESOLUTION_PATH_NOT_ALLOWED")
        if normalized.resolution_path == "authorized_goodwill":
            assert normalized.amount is not None
            if (
                not bool(action.inputs.get("authorized", False))
                or normalized.amount.currency != self.active_pact.goodwill_currency
                or normalized.amount.minor_units
                > self.active_pact.goodwill_limit_minor_units
            ):
                return self._audit(
                    action, "REQUIRE_APPROVAL", ReasonCode.POLICY_APPROVAL_REQUIRED.value,
                    slot="goodwill",
                )
        intent = OperationIntent(
            pact_id=self.active_pact.pact.pact_id,
            resolution_path=normalized.resolution_path,
            event_type=normalized.event_type,
            subject_id=self.active_pact.order_id.lower(),
            amount=normalized.amount,
            resource=normalized.resource,
            policy=self.active_pact.pact.policy,
            agent_id=action.actor,
            request_id=action.action_id,
            session_id=str(action.inputs.get("session_id", f"session-{action.action_id}")),
            trace_id=f"trace-{action.action_id}",
        )
        operation = canonicalize(intent, self.active_pact.pact)
        slot = self.active_pact.pact.slot_for(normalized.resolution_path)
        try:
            authority = self.engine.authorize(self.active_pact.pact, intent)
            audit = self._audit(
                action,
                authority.decision.value,
                authority.reason_code.value,
                operation_identity=operation.operation_key,
                slot=slot.name if slot else None,
                before=authority.reservation_state.value,
                after=authority.reservation_state.value,
            )
            if authority.decision is Decision.ALLOW:
                self.engine.begin_execution(authority)
                audit.reservation_state_after = ReservationState.EXECUTING.value
                self._pending[action.action_id] = (authority, audit)
            return audit
        except Exception:
            return self._audit(
                action,
                Decision.DEFER.value,
                "FIRESTORE_RESERVATION_UNAVAILABLE",
                operation_identity=operation.operation_key,
                slot=slot.name if slot else None,
            )

    def after_external_call(
        self, action: ScheduledAction, result: dict[str, Any]
    ) -> None:
        pending = self._pending.pop(action.action_id, None)
        if pending is None:
            return
        authority, audit = pending
        audit.external_call_executed = True
        status = result.get("status")
        if status == "OK":
            outcome = ExecutionOutcome.CONFIRMED
        elif status == "TIMEOUT":
            outcome = ExecutionOutcome.OUTCOME_UNKNOWN
        else:
            outcome = ExecutionOutcome.FAILED_AUTHORITATIVELY
        try:
            self.engine.record_outcome(authority, outcome)
            audit.reservation_state_after = outcome.value
        except Exception:
            # The call has happened. Never turn a post-call persistence failure into
            # permission for a retry; the committed EXECUTING state remains fail-closed.
            audit.reservation_state_after = ReservationState.EXECUTING.value
            audit.reason_code = "POST_CALL_STATE_PERSISTENCE_FAILED"
