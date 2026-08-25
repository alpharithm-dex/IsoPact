from __future__ import annotations

from isopact.domain.canonical import canonicalize
from isopact.domain.models import (
    AuthorizationDecision,
    ExecutionOutcome,
    OperationIntent,
    OutcomePact,
    ReservationState,
)

from .repository import ReservationRepository, ReservationRequest


class ReservationEngine:
    def __init__(self, repository: ReservationRepository) -> None:
        self._repository = repository

    def authorize(self, pact: OutcomePact, intent: OperationIntent) -> AuthorizationDecision:
        operation = canonicalize(intent, pact)
        return self._repository.reserve(ReservationRequest(pact, intent, operation))

    def begin_execution(self, decision: AuthorizationDecision) -> None:
        self._repository.transition(
            decision.pact_id,
            decision.operation_key,
            ReservationState.RESERVED,
            ReservationState.EXECUTING,
        )

    def record_outcome(
        self, decision: AuthorizationDecision, outcome: ExecutionOutcome
    ) -> None:
        target = ReservationState(outcome.value)
        self._repository.transition(
            decision.pact_id,
            decision.operation_key,
            ReservationState.EXECUTING,
            target,
        )

    def reconcile_unknown(
        self, decision: AuthorizationDecision, outcome: ExecutionOutcome
    ) -> None:
        if outcome is ExecutionOutcome.OUTCOME_UNKNOWN:
            raise ValueError("reconciliation requires authoritative success or failure")
        self._repository.transition(
            decision.pact_id,
            decision.operation_key,
            ReservationState.OUTCOME_UNKNOWN,
            ReservationState(outcome.value),
        )
