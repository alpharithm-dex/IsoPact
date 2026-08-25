from __future__ import annotations

from collections import defaultdict

from isopact.domain.models import Money
from isopact.evidence.identity import stable_id

from .models import (
    EconomicFact,
    EconomicFactKind,
    EconomicPhase,
    EconomicPolicy,
    EconomicPosition,
    ProtectionEvent,
    ProtectionEventType,
    ProtectionSummary,
)


PHASE_PRECEDENCE = {
    EconomicPhase.PROPOSED: 1,
    EconomicPhase.PENDING: 2,
    EconomicPhase.FAILED: 3,
    EconomicPhase.SETTLED: 4,
    EconomicPhase.REVERSED: 5,
    EconomicPhase.BLOCKED: 6,
}


def current_economic_facts(facts: tuple[EconomicFact, ...]) -> tuple[EconomicFact, ...]:
    current: dict[str, EconomicFact] = {}
    for fact in facts:
        existing = current.get(fact.economic_object_id)
        if existing is None or (
            fact.source_version,
            PHASE_PRECEDENCE[fact.phase],
            fact.occurred_at,
            fact.fact_id,
        ) > (
            existing.source_version,
            PHASE_PRECEDENCE[existing.phase],
            existing.occurred_at,
            existing.fact_id,
        ):
            current[fact.economic_object_id] = fact
    return tuple(sorted(current.values(), key=lambda item: item.economic_object_id))


class ProtectionLedger:
    @staticmethod
    def event(
        event_type: ProtectionEventType,
        fact: EconomicFact,
        reason_code: str,
        occurred_at: str,
    ) -> ProtectionEvent:
        event_id = stable_id(
            "protection",
            {
                "event_type": event_type.value,
                "economic_object_id": fact.economic_object_id,
                "operation_identity": fact.operation_identity,
                "amount": fact.amount.minor_units,
                "currency": fact.amount.currency,
            },
        )
        return ProtectionEvent(
            protection_event_id=event_id,
            event_type=event_type,
            economic_object_id=fact.economic_object_id,
            operation_identity=fact.operation_identity,
            amount=fact.amount,
            reason_code=reason_code,
            related_fact_ids=(fact.fact_id,),
            occurred_at=occurred_at,
        )

    @staticmethod
    def reduce(
        events: tuple[ProtectionEvent, ...], currency: str
    ) -> ProtectionSummary:
        unique = {event.protection_event_id: event for event in events}
        for event in unique.values():
            if event.amount.currency != currency:
                raise ValueError("protection event currency mismatch")
        prevented = sum(
            event.amount.minor_units
            for event in unique.values()
            if event.event_type is ProtectionEventType.INVALID_ACTION_PREVENTED
        )
        recovered = sum(
            event.amount.minor_units
            for event in unique.values()
            if event.event_type is ProtectionEventType.AUTHORIZED_VALUE_RECOVERED
        )
        delayed = sum(
            event.amount.minor_units
            for event in unique.values()
            if event.event_type is ProtectionEventType.LEGITIMATE_VALUE_DELAYED
        )
        return ProtectionSummary(
            currency=currency,
            invalid_actions_prevented=prevented,
            authorized_value_recovered=recovered,
            legitimate_value_delayed=delayed,
            protected_value=prevented + recovered - delayed,
            unique_event_count=len(unique),
            event_ids=tuple(sorted(unique)),
        )

    @staticmethod
    def recovered_event(
        fact: EconomicFact,
        *,
        conflict_ids: tuple[str, ...],
        compensation_execution_ids: tuple[str, ...],
        evidence_ids: tuple[str, ...],
        occurred_at: str,
    ) -> ProtectionEvent:
        if not conflict_ids or not compensation_execution_ids or not evidence_ids:
            raise ValueError("recovery requires conflict, execution, and authoritative evidence provenance")
        event_id = stable_id("protection", {"event_type": ProtectionEventType.AUTHORIZED_VALUE_RECOVERED.value, "economic_object_id": fact.economic_object_id, "operation_identity": fact.operation_identity, "amount": fact.amount.minor_units, "currency": fact.amount.currency})
        return ProtectionEvent(event_id, ProtectionEventType.AUTHORIZED_VALUE_RECOVERED, fact.economic_object_id, fact.operation_identity, fact.amount, "AUTHORITATIVE_REPLACEMENT_EXPOSURE_REMOVED", (fact.fact_id,), occurred_at, tuple(sorted(conflict_ids)), tuple(sorted(compensation_execution_ids)), tuple(sorted(evidence_ids)))


class EconomicReducer:
    @staticmethod
    def reduce(
        facts: tuple[EconomicFact, ...],
        policy: EconomicPolicy,
        protection_events: tuple[ProtectionEvent, ...] = (),
    ) -> tuple[EconomicPosition, tuple[EconomicFact, ...], ProtectionSummary]:
        current = current_economic_facts(facts)
        for fact in current:
            if fact.amount.currency != policy.currency:
                raise ValueError("economic fact currency mismatch")
        totals: dict[str, int] = defaultdict(int)
        provenance: list[str] = []
        for fact in current:
            amount = fact.amount.minor_units
            provenance.append(fact.fact_id)
            if fact.phase is EconomicPhase.BLOCKED:
                totals["blocked"] += amount
                continue
            if fact.kind is EconomicFactKind.REFUND:
                if fact.phase in {EconomicPhase.PROPOSED, EconomicPhase.PENDING}:
                    totals["pending_primary"] += amount
                    totals["authorized_primary"] += amount
                    totals["projected"] += amount
                elif fact.phase is EconomicPhase.SETTLED:
                    totals["settled_primary"] += amount
                    totals["authorized_primary"] += amount
                    totals["projected"] += amount
                    totals["settled"] += amount
                elif fact.phase is EconomicPhase.FAILED:
                    totals["failed_primary"] += amount
            elif fact.kind is EconomicFactKind.REPLACEMENT:
                if fact.phase in {EconomicPhase.PROPOSED, EconomicPhase.PENDING}:
                    totals["replacement_projected"] += amount
                    totals["authorized_primary"] += amount
                    totals["projected"] += amount
                elif fact.phase is EconomicPhase.SETTLED:
                    totals["replacement_committed"] += amount
                    totals["authorized_primary"] += amount
                    totals["projected"] += amount
                    totals["settled"] += amount
            elif fact.kind is EconomicFactKind.GOODWILL:
                if fact.phase in {EconomicPhase.PROPOSED, EconomicPhase.PENDING, EconomicPhase.SETTLED}:
                    totals["goodwill_authorized"] += amount
                    totals["projected"] += amount
                if fact.phase is EconomicPhase.SETTLED:
                    totals["goodwill_settled"] += amount
                    totals["settled"] += amount
            elif fact.kind is EconomicFactKind.OTHER_EXCEPTION:
                if fact.phase in {EconomicPhase.PROPOSED, EconomicPhase.PENDING, EconomicPhase.SETTLED}:
                    totals["other_exception"] += amount
                    totals["projected"] += amount
                if fact.phase is EconomicPhase.SETTLED:
                    totals["settled"] += amount
        protection = ProtectionLedger.reduce(protection_events, policy.currency)
        recoverable = sum(
            fact.amount.minor_units
            for fact in current
            if fact.kind is EconomicFactKind.REPLACEMENT
            and fact.preexisting_outside_gateway
            and fact.phase in {EconomicPhase.PROPOSED, EconomicPhase.PENDING}
            and fact.reversible is True
        )
        position = EconomicPosition(
            currency=policy.currency,
            captured_value=policy.captured_value,
            authorized_primary_value=totals["authorized_primary"],
            pending_primary_value=totals["pending_primary"],
            settled_primary_value=totals["settled_primary"],
            failed_primary_value=totals["failed_primary"],
            replacement_projected_value=totals["replacement_projected"],
            replacement_committed_value=totals["replacement_committed"],
            goodwill_authorized_value=totals["goodwill_authorized"],
            goodwill_settled_value=totals["goodwill_settled"],
            other_exception_value=totals["other_exception"],
            blocked_value=totals["blocked"],
            recovered_value=protection.authorized_value_recovered,
            legitimately_delayed_value=protection.legitimate_value_delayed,
            projected_total_compensation=totals["projected"],
            settled_total_compensation=totals["settled"],
            projected_excess_exposure=max(0, totals["projected"] - policy.captured_value),
            settled_excess_exposure=max(0, totals["settled"] - policy.captured_value),
            protected_value=protection.protected_value,
            recoverable_candidate_value=recoverable,
            provenance=tuple(sorted(provenance)),
        )
        return position, current, protection
