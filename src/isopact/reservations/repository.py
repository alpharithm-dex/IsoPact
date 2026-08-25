from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from isopact.domain.models import (
    AuthorizationDecision,
    CanonicalOperation,
    OperationIntent,
    OperationReservation,
    OutcomePact,
    ReservationState,
)


@dataclass(frozen=True, slots=True)
class ReservationRequest:
    pact: OutcomePact
    intent: OperationIntent
    operation: CanonicalOperation


class ReservationRepository(Protocol):
    def reserve(self, request: ReservationRequest) -> AuthorizationDecision: ...

    def transition(
        self, pact_id: str, operation_key: str, expected: ReservationState, target: ReservationState
    ) -> OperationReservation: ...

    def get(self, pact_id: str, operation_key: str) -> OperationReservation | None: ...

