from __future__ import annotations

from isopact.domain.models import Money

from .economics import ProtectionLedger
from .models import EconomicFact, EconomicFactKind, EconomicPhase, EconomicPolicy, ProtectionEventType


NOW = "2026-08-23T20:00:00Z"


def stage6_policy(*, rule_version: str = "1") -> EconomicPolicy:
    return EconomicPolicy(
        policy_id="commerce_missing_order_v1",
        authorization_policy_version="1",
        evaluation_rule_set_id="commerce_missing_order_rules",
        evaluation_rule_set_version=rule_version,
        current_policy_version="2",
        currency="USD",
        captured_value=20_000,
        goodwill_limit=5_000,
    )


def fact(
    object_id: str,
    kind: EconomicFactKind,
    phase: EconomicPhase,
    amount: int,
    *,
    intent: str,
    scope: str,
    version: int = 1,
    executed: bool = True,
    authorized: bool = True,
    reversible: bool | None = None,
    preexisting: bool = False,
) -> EconomicFact:
    return EconomicFact(
        fact_id=f"fact_{object_id}_{version}_{phase.value.lower()}",
        economic_object_id=object_id,
        semantic_intent_id=intent,
        economic_scope=scope,
        kind=kind,
        phase=phase,
        amount=Money("USD", amount),
        subject_id="order_200",
        operation_identity=f"op_{object_id}",
        external_object_id=object_id,
        source_system="stage2_simulator",
        source_version=version,
        occurred_at=f"2026-08-23T20:00:{version:02d}Z",
        executed=executed,
        authorized=authorized,
        external_state=phase.value,
        reversible=reversible,
        preexisting_outside_gateway=preexisting,
    )


def unmanaged_facts() -> tuple[EconomicFact, ...]:
    return (
        fact("refund_a", EconomicFactKind.REFUND, EconomicPhase.PENDING, 20_000, intent="missing-order-refund", scope="primary:full"),
        fact("replacement", EconomicFactKind.REPLACEMENT, EconomicPhase.PROPOSED, 20_000, intent="missing-order-replacement", scope="primary:full", reversible=False),
        fact("goodwill", EconomicFactKind.GOODWILL, EconomicPhase.SETTLED, 5_000, intent="delay-goodwill", scope="exception:delay"),
        fact("refund_b", EconomicFactKind.REFUND, EconomicPhase.PENDING, 20_000, intent="missing-order-refund", scope="primary:full"),
    )


def protected_facts(*, settled: bool) -> tuple[EconomicFact, ...]:
    refund_phase = EconomicPhase.SETTLED if settled else EconomicPhase.PENDING
    return (
        fact("refund_a", EconomicFactKind.REFUND, refund_phase, 20_000, intent="missing-order-refund", scope="primary:full"),
        fact("replacement", EconomicFactKind.REPLACEMENT, EconomicPhase.BLOCKED, 20_000, intent="missing-order-replacement", scope="primary:full", executed=False),
        fact("goodwill", EconomicFactKind.GOODWILL, EconomicPhase.SETTLED, 5_000, intent="delay-goodwill", scope="exception:delay"),
        fact("refund_b", EconomicFactKind.REFUND, EconomicPhase.BLOCKED, 20_000, intent="missing-order-refund", scope="primary:full", executed=False),
    )


def protected_events(facts: tuple[EconomicFact, ...]):
    blocked = {item.economic_object_id: item for item in facts if item.phase is EconomicPhase.BLOCKED}
    return (
        ProtectionLedger.event(ProtectionEventType.INVALID_ACTION_PREVENTED, blocked["replacement"], "EXCLUSIVE_RESOLUTION_CONFLICT", NOW),
        ProtectionLedger.event(ProtectionEventType.INVALID_ACTION_PREVENTED, blocked["refund_b"], "DUPLICATE_OPERATION", NOW),
    )


def preexisting_divergence_facts() -> tuple[EconomicFact, ...]:
    return (
        fact("refund_a", EconomicFactKind.REFUND, EconomicPhase.PENDING, 20_000, intent="missing-order-refund", scope="primary:full"),
        fact("replacement", EconomicFactKind.REPLACEMENT, EconomicPhase.PROPOSED, 20_000, intent="missing-order-replacement", scope="primary:full", reversible=True, preexisting=True),
        fact("goodwill", EconomicFactKind.GOODWILL, EconomicPhase.SETTLED, 5_000, intent="delay-goodwill", scope="exception:delay"),
    )
