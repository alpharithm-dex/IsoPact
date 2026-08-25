from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any

from google.cloud import firestore

from isopact.domain.models import (
    AuthorizationDecision,
    CanonicalOperation,
    Decision,
    Money,
    OperationReservation,
    PolicyVersion,
    ReasonCode,
    ReservationState,
    ResolutionSlot,
)

from .repository import ReservationRequest


RELEASING_STATES = {
    ReservationState.FAILED_AUTHORITATIVELY,
    ReservationState.REVERSED,
    ReservationState.EXPIRED,
}


@dataclass(frozen=True, slots=True)
class ReservationPlan:
    decision: Decision
    reason_code: ReasonCode
    write_reservation: bool


def evaluate_reservation_snapshot(
    existing_state: ReservationState | None, *, slot_occupied: bool
) -> ReservationPlan:
    """Pure retry-safe decision logic used by the Firestore callback."""
    if existing_state is ReservationState.FAILED_AUTHORITATIVELY:
        return ReservationPlan(
            Decision.ALLOW, ReasonCode.AUTHORITATIVE_FAILURE_RETRY, True
        )
    if existing_state in {ReservationState.RESERVED, ReservationState.EXECUTING}:
        return ReservationPlan(Decision.DEFER, ReasonCode.OPERATION_IN_PROGRESS, False)
    if existing_state is ReservationState.OUTCOME_UNKNOWN:
        return ReservationPlan(
            Decision.DEFER, ReasonCode.EXTERNAL_OUTCOME_UNKNOWN, False
        )
    if existing_state is not None:
        return ReservationPlan(Decision.BLOCK, ReasonCode.DUPLICATE_OPERATION, False)
    if slot_occupied:
        return ReservationPlan(
            Decision.BLOCK, ReasonCode.EXCLUSIVE_RESOLUTION_CONFLICT, False
        )
    return ReservationPlan(Decision.ALLOW, ReasonCode.AUTHORITY_RESERVED, True)


def _reservation_document(reservation: OperationReservation) -> dict[str, Any]:
    operation = reservation.canonical_operation
    return {
        "pact_id": reservation.pact_id,
        "operation_key": reservation.operation_key,
        "canonical_operation": {
            "pact_id": operation.pact_id,
            "resolution_path": operation.resolution_path,
            "event_type": operation.event_type,
            "subject_id": operation.subject_id,
            "normalized_value": operation.normalized_value,
            "operation_key": operation.operation_key,
            "policy_id": operation.policy.policy_id,
            "policy_version": operation.policy.version,
        },
        "slot": reservation.slot.name if reservation.slot else None,
        "state": reservation.state.value,
        "authorization_policy_id": reservation.authorization_policy.policy_id,
        "authorization_policy_version": reservation.authorization_policy.version,
        "first_agent_id": reservation.first_agent_id,
        "attempt_count": reservation.attempt_count,
        "state_history": [state.value for state in reservation.state_history],
        "updated_at": firestore.SERVER_TIMESTAMP,
    }


def _reservation_from_document(data: dict[str, Any]) -> OperationReservation:
    operation_data = data["canonical_operation"]
    policy = PolicyVersion(
        operation_data["policy_id"], operation_data["policy_version"]
    )
    operation = CanonicalOperation(
        pact_id=operation_data["pact_id"],
        resolution_path=operation_data["resolution_path"],
        event_type=operation_data["event_type"],
        subject_id=operation_data["subject_id"],
        normalized_value=operation_data["normalized_value"],
        operation_key=operation_data["operation_key"],
        policy=policy,
    )
    return OperationReservation(
        pact_id=data["pact_id"],
        operation_key=data["operation_key"],
        canonical_operation=operation,
        slot=ResolutionSlot(data["slot"]) if data.get("slot") else None,
        state=ReservationState(data["state"]),
        authorization_policy=PolicyVersion(
            data["authorization_policy_id"], data["authorization_policy_version"]
        ),
        first_agent_id=data["first_agent_id"],
        attempt_count=int(data.get("attempt_count", 1)),
        state_history=tuple(
            ReservationState(value) for value in data.get("state_history", ["RESERVED"])
        ),
    )


class FirestoreReservationRepository:
    """Live Firestore repository; no process-local lock provides safety authority."""

    def __init__(
        self,
        project: str,
        database: str = "(default)",
        *,
        client: firestore.Client | None = None,
    ) -> None:
        self.project = project
        self.database = database
        self.client = client or firestore.Client(project=project, database=database)
        self._metric_lock = Lock()
        self.transaction_callback_invocations = 0

    def _pact(self, pact_id: str):
        return self.client.collection("pacts").document(pact_id)

    def activate(self, pact_id: str, data: dict[str, Any]) -> None:
        self._pact(pact_id).set({**data, "updated_at": firestore.SERVER_TIMESTAMP})

    def _count_callback(self) -> None:
        with self._metric_lock:
            self.transaction_callback_invocations += 1

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
        pact_ref = self._pact(request.pact.pact_id)
        operation_ref = pact_ref.collection("operations").document(
            request.operation.operation_key
        )
        slot = request.pact.slot_for(request.operation.resolution_path)
        slot_ref = pact_ref.collection("slots").document(slot.name) if slot else None
        transaction = self.client.transaction(max_attempts=10)

        @firestore.transactional
        def reserve_transaction(txn):
            self._count_callback()
            operation_snapshot = operation_ref.get(transaction=txn)
            slot_snapshot = slot_ref.get(transaction=txn) if slot_ref else None
            existing_state = None
            if operation_snapshot.exists:
                existing_state = ReservationState(operation_snapshot.to_dict()["state"])
            plan = evaluate_reservation_snapshot(
                existing_state,
                slot_occupied=bool(slot_snapshot is not None and slot_snapshot.exists),
            )
            if operation_snapshot.exists:
                existing = _reservation_from_document(operation_snapshot.to_dict())
                if plan.reason_code is ReasonCode.AUTHORITATIVE_FAILURE_RETRY:
                    retried = existing.retry_under(
                        request.intent.policy, request.intent.agent_id
                    )
                    txn.set(operation_ref, _reservation_document(retried))
                    if slot_ref:
                        txn.set(
                            slot_ref,
                            {
                                "operation_key": retried.operation_key,
                                "resolution_path": retried.canonical_operation.resolution_path,
                                "updated_at": firestore.SERVER_TIMESTAMP,
                            },
                        )
                    return self._decision(
                        retried,
                        Decision.ALLOW,
                        ReasonCode.AUTHORITATIVE_FAILURE_RETRY,
                    )
                return self._decision(existing, plan.decision, plan.reason_code)

            placeholder = OperationReservation(
                pact_id=request.pact.pact_id,
                operation_key=request.operation.operation_key,
                canonical_operation=request.operation,
                slot=slot,
                state=ReservationState.RESERVED,
                authorization_policy=request.intent.policy,
                first_agent_id=request.intent.agent_id,
            )
            if plan.reason_code is ReasonCode.EXCLUSIVE_RESOLUTION_CONFLICT:
                return self._decision(
                    placeholder,
                    Decision.BLOCK,
                    ReasonCode.EXCLUSIVE_RESOLUTION_CONFLICT,
                    slot_snapshot.to_dict().get("operation_key"),
                )
            txn.create(operation_ref, _reservation_document(placeholder))
            if slot_ref:
                txn.create(
                    slot_ref,
                    {
                        "operation_key": placeholder.operation_key,
                        "resolution_path": request.operation.resolution_path,
                        "updated_at": firestore.SERVER_TIMESTAMP,
                    },
                )
            return self._decision(
                placeholder, Decision.ALLOW, ReasonCode.AUTHORITY_RESERVED
            )

        return reserve_transaction(transaction)

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
        if target not in allowed.get(expected, set()):
            raise ValueError(f"invalid reservation transition {expected} -> {target}")
        pact_ref = self._pact(pact_id)
        operation_ref = pact_ref.collection("operations").document(operation_key)
        transaction = self.client.transaction(max_attempts=10)

        @firestore.transactional
        def transition_transaction(txn):
            self._count_callback()
            snapshot = operation_ref.get(transaction=txn)
            if not snapshot.exists:
                raise KeyError(f"unknown reservation {pact_id}/{operation_key}")
            current = _reservation_from_document(snapshot.to_dict())
            if current.state is not expected:
                raise ValueError(f"expected {expected}, found {current.state}")
            updated = current.transition(target)
            txn.set(operation_ref, _reservation_document(updated))
            if target in RELEASING_STATES and current.slot:
                slot_ref = pact_ref.collection("slots").document(current.slot.name)
                txn.delete(slot_ref)
            return updated

        return transition_transaction(transaction)

    def get(self, pact_id: str, operation_key: str) -> OperationReservation | None:
        snapshot = (
            self._pact(pact_id)
            .collection("operations")
            .document(operation_key)
            .get()
        )
        return _reservation_from_document(snapshot.to_dict()) if snapshot.exists else None

    def cleanup_pact(self, pact_id: str) -> None:
        """Delete exactly one proof pact and its known subcollections."""
        pact_ref = self._pact(pact_id)
        for name in ("reservation_history", "operations", "slots", "executions"):
            for snapshot in pact_ref.collection(name).stream():
                snapshot.reference.delete()
        pact_ref.delete()
