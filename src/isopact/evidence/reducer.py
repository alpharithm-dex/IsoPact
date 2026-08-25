from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import Evidence, ImmediateState, PactLifecycle, SettlementEvaluation


FINALITY = {
    ImmediateState.UNKNOWN: 0,
    ImmediateState.ACCEPTED: 1,
    ImmediateState.PENDING: 1,
    ImmediateState.CLOSED: 1,
    ImmediateState.COMPLETE: 1,
    ImmediateState.SUCCEEDED: 2,
    ImmediateState.FAILED: 2,
    ImmediateState.REVERSED: 3,
}


AUTHORITATIVE_TRANSITIONS = {
    "stripe": {
        ImmediateState.PENDING: frozenset({ImmediateState.SUCCEEDED, ImmediateState.FAILED}),
        ImmediateState.SUCCEEDED: frozenset({ImmediateState.REVERSED}),
        ImmediateState.FAILED: frozenset(),
        ImmediateState.REVERSED: frozenset(),
    }
}


def evidence_projection(evidence: Evidence) -> dict[str, Any]:
    return {
        "evidence_id": evidence.evidence_id,
        "evidence_type": evidence.evidence_type,
        "source_system": evidence.source_system,
        "resolution_path": evidence.resolution_path,
        "state": evidence.resolved_state.value,
        "rank": int(evidence.evidence_rank),
        "attempt": evidence.operation_attempt,
        "source_sequence": evidence.source_sequence,
        "occurred_at": evidence.occurred_at,
        "external_object_id": evidence.external_object_id,
    }


def should_replace_resolved(
    current: dict[str, Any] | None, incoming: Evidence
) -> bool:
    """Monotonic reducer: attempt, trust rank, finality, then source event time."""
    if current is None:
        return True
    current_attempt = int(current.get("attempt", 1))
    if incoming.operation_attempt != current_attempt:
        return incoming.operation_attempt > current_attempt
    current_rank = int(current["rank"])
    if int(incoming.evidence_rank) != current_rank:
        return int(incoming.evidence_rank) < current_rank
    current_state = ImmediateState(current["state"])
    if int(incoming.evidence_rank) == 1 and current_rank == 1:
        current_sequence = current.get("source_sequence")
        if incoming.resolved_state == current_state:
            if incoming.source_sequence is not None and current_sequence is not None:
                return incoming.source_sequence > int(current_sequence)
            return incoming.occurred_at > str(current["occurred_at"])
        if incoming.source_sequence is None or current_sequence is None:
            return False
        if incoming.source_sequence <= int(current_sequence):
            return False
        allowed = AUTHORITATIVE_TRANSITIONS.get(incoming.source_system, {}).get(
            current_state, frozenset()
        )
        return incoming.resolved_state in allowed
    if FINALITY[incoming.resolved_state] != FINALITY[current_state]:
        return FINALITY[incoming.resolved_state] > FINALITY[current_state]
    return incoming.occurred_at > str(current["occurred_at"])


def reduce_operation(
    current: dict[str, Any] | None, incoming: Evidence
) -> tuple[dict[str, Any], bool]:
    if should_replace_resolved(current, incoming):
        return evidence_projection(incoming), True
    assert current is not None
    return current, False


@dataclass(frozen=True, slots=True)
class EvaluationPlan:
    state: PactLifecycle
    reason_codes: tuple[str, ...]
    qualifying_evidence_ids: tuple[str, ...]


def is_primary_resolution(root: dict[str, Any], resolution_path: str | None) -> bool:
    """Return whether a path occupies the primary-compensation slot.

    Additive remedies such as goodwill must never replace the primary refund or
    replacement selected for settlement.
    """
    if not resolution_path:
        return False
    return resolution_path in set(root.get("exclusive_slots", {}).get("primary_compensation", ()))


def evaluate_graph(root: dict[str, Any]) -> EvaluationPlan:
    current_state = PactLifecycle(root.get("graph_state", "OPEN"))
    if current_state is PactLifecycle.SETTLED:
        ids = tuple(root.get("settlement_evidence_ids", ()))
        return EvaluationPlan(PactLifecycle.SETTLED, ("SETTLEMENT_ALREADY_COMMITTED",), ids)
    selected = root.get("selected_resolution")
    if not selected:
        return EvaluationPlan(PactLifecycle.OPEN, ("NO_SELECTED_RESOLUTION",), ())
    operations = [
        value
        for value in root.get("resolved_operations", {}).values()
        if value.get("resolution_path") == selected
    ]
    if not operations:
        return EvaluationPlan(PactLifecycle.PENDING, ("AWAITING_EXTERNAL_STATE",), ())
    failures = [
        value
        for value in operations
        if value.get("state") == ImmediateState.FAILED.value and int(value.get("rank", 5)) <= 2
    ]
    if failures:
        return EvaluationPlan(PactLifecycle.OPEN, ("AUTHORITATIVE_RESOLUTION_FAILURE",), ())
    required = tuple(root.get("completion_evidence", {}).get(selected, ()))
    maximum_rank = int(root.get("evidence_max_rank", {}).get(selected, 1))
    qualifying = [
        value
        for value in operations
        if value.get("state") == ImmediateState.SUCCEEDED.value
        and value.get("evidence_type") in required
        and int(value.get("rank", 5)) <= maximum_rank
    ]
    if qualifying and required:
        return EvaluationPlan(
            PactLifecycle.SETTLED,
            ("TRUSTED_COMPLETION_EVIDENCE_SATISFIED",),
            tuple(sorted({value["evidence_id"] for value in qualifying})),
        )
    return EvaluationPlan(
        PactLifecycle.PENDING,
        ("REQUIRED_AUTHORITATIVE_EVIDENCE_MISSING",),
        (),
    )


def settlement_evaluation(
    root: dict[str, Any], revision: int, evaluated_at: str
) -> SettlementEvaluation:
    plan = evaluate_graph(root)
    selected = root.get("selected_resolution")
    required = tuple(root.get("completion_evidence", {}).get(selected, ())) if selected else ()
    return SettlementEvaluation(
        evaluation_id=f"evaluation_{revision:08d}",
        pact_id=root["pact_id"],
        input_revision=revision,
        selected_resolution=selected,
        required_evidence=required,
        qualifying_evidence_ids=plan.qualifying_evidence_ids,
        result=plan.state,
        reason_codes=plan.reason_codes,
        evaluated_at=evaluated_at,
    )
