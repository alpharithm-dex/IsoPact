from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from isopact.compiler.models import (
    AuthoritativeCaseContext,
    TrustedPolicy,
    ValidatedOutcomePactDraft,
)
from isopact.domain.models import Money, OutcomePact, PolicyVersion


@dataclass(frozen=True, slots=True)
class ActiveOutcomePact:
    pact: OutcomePact
    order_id: str
    customer_id: str
    ticket_id: str
    goodwill_limit_minor_units: int
    goodwill_currency: str
    completion_evidence: dict[str, tuple[str, ...]]
    evidence_max_rank: dict[str, int]
    evaluation_rule_set_id: str = "commerce_missing_order_rules"
    evaluation_rule_set_version: str = "1"
    activation_source: str = "VALIDATED_DRAFT_AND_TRUSTED_POLICY"

    def to_document(self) -> dict[str, object]:
        return {
            "pact_id": self.pact.pact_id,
            "status": "ACTIVE",
            "order_id": self.order_id,
            "customer_id": self.customer_id,
            "ticket_id": self.ticket_id,
            "transaction": {
                "minor_units": self.pact.transaction.minor_units,
                "currency": self.pact.transaction.currency,
            },
            "allowed_resolution_paths": sorted(self.pact.allowed_resolution_paths),
            "exclusive_slots": {
                name: sorted(paths) for name, paths in self.pact.exclusive_slots.items()
            },
            "policy_id": self.pact.policy.policy_id,
            "policy_version": self.pact.policy.version,
            "goodwill_limit_minor_units": self.goodwill_limit_minor_units,
            "goodwill_currency": self.goodwill_currency,
            "completion_evidence": {
                path: list(events) for path, events in self.completion_evidence.items()
            },
            "evidence_max_rank": dict(self.evidence_max_rank),
            "authorization_policy_version": self.pact.policy.reference,
            "evaluation_rule_set_id": self.evaluation_rule_set_id,
            "evaluation_rule_set_version": self.evaluation_rule_set_version,
            "activation_source": self.activation_source,
        }


def activate_validated_draft(
    draft: ValidatedOutcomePactDraft,
    context: AuthoritativeCaseContext,
    policy: TrustedPolicy,
    *,
    namespace: str = "active",
) -> ActiveOutcomePact:
    if draft.activation_state != "DRAFT_NOT_ENFORCEABLE":
        raise ValueError("activation requires a non-enforceable validated draft")
    if (draft.policy_id, draft.policy_version) != (policy.policy_id, policy.version):
        raise ValueError("trusted policy does not match validated draft")
    if set(draft.allowed_resolution_paths) - policy.allowed_resolution_paths:
        raise ValueError("draft contains a path not resolved by trusted policy")
    order_id = draft.subjects.get("order_id")
    customer_id = draft.subjects.get("customer_id")
    order = next(
        (
            item
            for item in context.orders
            if item.order_id == order_id and item.customer_id == customer_id
        ),
        None,
    )
    if order is None:
        raise ValueError("authoritative subject context does not match draft")
    seed = json.dumps(
        {
            "namespace": namespace,
            "order_id": order.order_id,
            "policy_id": policy.policy_id,
            "policy_version": policy.version,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    pact_id = f"pact_{namespace}_{hashlib.sha256(seed.encode()).hexdigest()[:20]}"
    # The validated draft proves the requested concepts; activation resolves the
    # complete trusted policy envelope, including independently permitted goodwill.
    active_paths = frozenset(policy.allowed_resolution_paths)
    slots = {
        policy.exclusive_slot: frozenset(
            path
            for path in active_paths
            if path in {"successful_refund", "confirmed_replacement"}
        ),
        "goodwill": frozenset(
            path for path in active_paths if path == "authorized_goodwill"
        ),
    }
    return ActiveOutcomePact(
        pact=OutcomePact(
            pact_id=pact_id,
            transaction=Money(order.currency, order.captured_minor_units),
            allowed_resolution_paths=active_paths,
            exclusive_slots=slots,
            policy=PolicyVersion(policy.policy_id, policy.version),
        ),
        order_id=order.order_id,
        customer_id=order.customer_id,
        ticket_id=context.ticket_id,
        goodwill_limit_minor_units=draft.goodwill_limit_minor_units,
        goodwill_currency=draft.goodwill_currency,
        completion_evidence={
            path: tuple(events) for path, events in policy.completion_evidence.items()
        },
        evidence_max_rank=dict(policy.evidence_max_rank),
        evaluation_rule_set_id=policy.evaluation_rule_set_id,
        evaluation_rule_set_version=policy.evaluation_rule_set_version,
    )
