from __future__ import annotations

from collections import defaultdict
from threading import Lock

from isopact.domain.models import (
    AuthorizationDecision,
    Decision,
    OperationReservation,
    ReasonCode,
    ReservationState,
)

from .repository import ReservationRequest


class InMemoryReservationRepository:
    """Concurrency-safe repository with independent per-pact critical sections.

    The registry lock protects only creation of pact locks. Reservation operations for
    different pacts never share an execution critical section.
    """

    def __init__(self) -> None:
        self._registry_lock = Lock()
        self._pact_locks: dict[str, Lock] = {}
        self._reservations: dict[tuple[str, str], OperationReservation] = {}
        self._slots: dict[tuple[str, str], str] = {}

    def _lock_for(self, pact_id: str) -> Lock:
        with self._registry_lock:
            return self._pact_locks.setdefault(pact_id, Lock())

    @staticmethod
    def _decision(
        reservation: OperationReservation,
        decision: Decision,
        reason: ReasonCode,
        conflict: str | None = None,
    ) -> AuthorizationDecision:
        return AuthorizationDecision(
            pact_id=reservation.pact_id,
            operation_key=reservation.operation_key,
            requested_resolution_slot=reservation.slot.name if reservation.slot else None,
            reservation_state=reservation.state,
            decision=decision,
            reason_code=reason,
            policy_reference=reservation.authorization_policy.reference,
            existing_conflicting_reservation=conflict,
        )

    def reserve(self, request: ReservationRequest) -> AuthorizationDecision:
        key = (request.pact.pact_id, request.operation.operation_key)
        slot = request.pact.slot_for(request.operation.resolution_path)
        with self._lock_for(request.pact.pact_id):
            existing = self._reservations.get(key)
            if existing is not None:
                if existing.state is ReservationState.FAILED_AUTHORITATIVELY:
                    retried = existing.retry_under(request.intent.policy, request.intent.agent_id)
                    self._reservations[key] = retried
                    if slot:
                        self._slots[(request.pact.pact_id, slot.name)] = request.operation.operation_key
                    return self._decision(
                        retried, Decision.ALLOW, ReasonCode.AUTHORITATIVE_FAILURE_RETRY
                    )
                if existing.state in {ReservationState.RESERVED, ReservationState.EXECUTING}:
                    return self._decision(
                        existing, Decision.DEFER, ReasonCode.OPERATION_IN_PROGRESS
                    )
                if existing.state is ReservationState.OUTCOME_UNKNOWN:
                    return self._decision(
                        existing, Decision.DEFER, ReasonCode.EXTERNAL_OUTCOME_UNKNOWN
                    )
                return self._decision(existing, Decision.BLOCK, ReasonCode.DUPLICATE_OPERATION)

            if slot is not None:
                slot_key = (request.pact.pact_id, slot.name)
                conflicting_key = self._slots.get(slot_key)
                if conflicting_key is not None:
                    conflicting = self._reservations[(request.pact.pact_id, conflicting_key)]
                    if conflicting.state not in {
                        ReservationState.FAILED_AUTHORITATIVELY,
                        ReservationState.REVERSED,
                        ReservationState.EXPIRED,
                    }:
                        placeholder = OperationReservation(
                            pact_id=request.pact.pact_id,
                            operation_key=request.operation.operation_key,
                            canonical_operation=request.operation,
                            slot=slot,
                            state=ReservationState.RESERVED,
                            authorization_policy=request.intent.policy,
                            first_agent_id=request.intent.agent_id,
                        )
                        return self._decision(
                            placeholder,
                            Decision.BLOCK,
                            ReasonCode.EXCLUSIVE_RESOLUTION_CONFLICT,
                            conflicting_key,
                        )

            reservation = OperationReservation(
                pact_id=request.pact.pact_id,
                operation_key=request.operation.operation_key,
                canonical_operation=request.operation,
                slot=slot,
                state=ReservationState.RESERVED,
                authorization_policy=request.intent.policy,
                first_agent_id=request.intent.agent_id,
            )
            self._reservations[key] = reservation
            if slot:
                self._slots[(request.pact.pact_id, slot.name)] = request.operation.operation_key
            return self._decision(reservation, Decision.ALLOW, ReasonCode.AUTHORITY_RESERVED)

    def transition(
        self,
        pact_id: str,
        operation_key: str,
        expected: ReservationState,
        target: ReservationState,
    ) -> OperationReservation:
        allowed = {
            ReservationState.RESERVED: {
                ReservationState.EXECUTING,
                ReservationState.EXPIRED,
            },
            ReservationState.EXECUTING: {
                ReservationState.CONFIRMED,
                ReservationState.FAILED_AUTHORITATIVELY,
                ReservationState.OUTCOME_UNKNOWN,
            },
            ReservationState.OUTCOME_UNKNOWN: {
                ReservationState.CONFIRMED,
                ReservationState.FAILED_AUTHORITATIVELY,
            },
            ReservationState.CONFIRMED: {ReservationState.REVERSED},
        }
        with self._lock_for(pact_id):
            key = (pact_id, operation_key)
            current = self._reservations[key]
            if current.state is not expected:
                raise ValueError(f"expected {expected}, found {current.state}")
            if target not in allowed.get(expected, set()):
                raise ValueError(f"invalid reservation transition {expected} -> {target}")
            updated = current.transition(target)
            self._reservations[key] = updated
            if target in {
                ReservationState.FAILED_AUTHORITATIVELY,
                ReservationState.REVERSED,
                ReservationState.EXPIRED,
            } and current.slot:
                self._slots.pop((pact_id, current.slot.name), None)
            return updated

    def get(self, pact_id: str, operation_key: str) -> OperationReservation | None:
        with self._lock_for(pact_id):
            return self._reservations.get((pact_id, operation_key))

