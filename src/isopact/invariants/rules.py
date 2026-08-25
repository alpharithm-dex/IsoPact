from __future__ import annotations

from collections import defaultdict
from typing import Any

from isopact.evidence.identity import stable_id

from .models import (
    EconomicFact,
    EconomicFactKind,
    EconomicPhase,
    EvaluationResult,
    InvariantRule,
    ResponseCategory,
    RuleContext,
    RuleEvaluation,
    Severity,
)


ACTIVE_PHASES = {EconomicPhase.PROPOSED, EconomicPhase.PENDING, EconomicPhase.SETTLED}


def _evaluation(
    context: RuleContext,
    rule: InvariantRule,
    result: EvaluationResult,
    reason_code: str,
    *,
    facts: tuple[EconomicFact, ...] = (),
    amounts: dict[str, int] | None = None,
    explanation: str,
    responses: tuple[ResponseCategory, ...] = (),
    inputs: dict[str, Any] | None = None,
) -> RuleEvaluation:
    fact_ids = tuple(sorted(fact.fact_id for fact in facts))
    evaluation_id = stable_id(
        "rule_eval",
        {
            "pact_id": context.pact_id,
            "revision": context.graph_revision,
            "rule": rule.rule_id,
            "version": rule.rule_version,
            "facts": fact_ids,
            "result": result.value,
        },
    )
    return RuleEvaluation(
        evaluation_id=evaluation_id,
        pact_id=context.pact_id,
        rule_id=rule.rule_id,
        rule_version=rule.rule_version,
        result=result,
        severity=rule.severity,
        reason_code=reason_code,
        input_facts=inputs or {"fact_ids": list(fact_ids)},
        evidence_ids=tuple(sorted({item for fact in facts for item in fact.related_evidence_ids})),
        economic_amounts=amounts or {},
        conflicting_operation_ids=tuple(
            sorted({fact.operation_identity for fact in facts if fact.operation_identity})
        ),
        explanation=explanation,
        permitted_response_categories=responses,
        authorization_policy_version=context.policy.authorization_policy_reference,
        evaluation_policy_version=context.policy.evaluation_policy_reference,
    )


def refund_value_bound(context: RuleContext, rule: InvariantRule) -> RuleEvaluation:
    refunds = tuple(
        fact for fact in context.current_facts
        if fact.kind is EconomicFactKind.REFUND and fact.phase in ACTIVE_PHASES
    )
    total = sum(fact.amount.minor_units for fact in refunds)
    limit = context.policy.captured_value + context.policy.authorized_refund_exception
    if total <= limit:
        return _evaluation(
            context, rule, EvaluationResult.PASS, "REFUND_VALUE_WITHIN_BOUND",
            facts=refunds, amounts={"refund_value": total, "refund_limit": limit},
            explanation=f"Active refund value {total} is within trusted limit {limit}.",
        )
    return _evaluation(
        context, rule, EvaluationResult.FAIL, "REFUND_VALUE_BOUND_EXCEEDED",
        facts=refunds, amounts={"refund_value": total, "refund_limit": limit, "excess": total - limit},
        explanation=f"Active refund value {total} exceeds trusted limit {limit} by {total - limit} minor units.",
        responses=(ResponseCategory.BLOCK_NEW_ACTION, ResponseCategory.EVALUATE_REGISTERED_COMPENSATION),
    )


def primary_resolution_exclusive(context: RuleContext, rule: InvariantRule) -> RuleEvaluation:
    refunds = tuple(f for f in context.current_facts if f.kind is EconomicFactKind.REFUND and f.phase in ACTIVE_PHASES)
    replacements = tuple(f for f in context.current_facts if f.kind is EconomicFactKind.REPLACEMENT and f.phase in ACTIVE_PHASES)
    if not refunds or not replacements or context.policy.dual_compensation_exception:
        return _evaluation(
            context, rule, EvaluationResult.PASS, "PRIMARY_RESOLUTION_EXCLUSIVE",
            facts=(*refunds, *replacements), explanation="No unapproved refund/replacement overlap exists.",
        )
    refund_value = sum(item.amount.minor_units for item in refunds)
    replacement_value = sum(item.amount.minor_units for item in replacements)
    return _evaluation(
        context, rule, EvaluationResult.FAIL, "PRIMARY_RESOLUTION_OVERLAP",
        facts=(*refunds, *replacements),
        amounts={"refund_value": refund_value, "replacement_value": replacement_value, "overlap": min(refund_value, replacement_value)},
        explanation="Refund and replacement coexist without a trusted dual-compensation exception.",
        responses=(ResponseCategory.BLOCK_NEW_ACTION, ResponseCategory.EVALUATE_REGISTERED_COMPENSATION),
    )


def duplicate_semantic_compensation(context: RuleContext, rule: InvariantRule) -> RuleEvaluation:
    groups: dict[tuple[str, str], list[EconomicFact]] = defaultdict(list)
    for fact in context.current_facts:
        if fact.kind in {EconomicFactKind.REFUND, EconomicFactKind.REPLACEMENT} and fact.phase in ACTIVE_PHASES:
            groups[(fact.semantic_intent_id, fact.economic_scope)].append(fact)
    duplicates = tuple(
        fact for group in groups.values() if len(group) > 1 for fact in group
    )
    if not duplicates:
        return _evaluation(
            context, rule, EvaluationResult.PASS, "NO_DUPLICATE_SEMANTIC_COMPENSATION",
            explanation="Each active primary compensation has a distinct approved economic intent scope.",
        )
    invalid = sum(item.amount.minor_units for group in groups.values() if len(group) > 1 for item in group) - sum(
        max(item.amount.minor_units for item in group) for group in groups.values() if len(group) > 1
    )
    return _evaluation(
        context, rule, EvaluationResult.FAIL, "DUPLICATE_SEMANTIC_COMPENSATION",
        facts=duplicates, amounts={"duplicate_value": invalid},
        explanation="Distinct external objects represent the same primary economic intent and scope.",
        responses=(ResponseCategory.BLOCK_NEW_ACTION, ResponseCategory.EVALUATE_REGISTERED_COMPENSATION),
    )


def completion_requires_evidence(context: RuleContext, rule: InvariantRule) -> RuleEvaluation:
    if context.settlement_evidence_satisfied:
        return _evaluation(
            context, rule, EvaluationResult.PASS, "COMPLETION_EVIDENCE_SATISFIED",
            explanation="The selected resolution has policy-qualified authoritative evidence.",
        )
    reason = "UNSUPPORTED_COMPLETION_CLAIM" if context.ticket_closed or context.agent_complete else "COMPLETION_EVIDENCE_PENDING"
    return _evaluation(
        context, rule, EvaluationResult.UNKNOWN, reason,
        explanation="Ticket or agent completion cannot substitute for required settlement evidence.",
        responses=(ResponseCategory.WAIT_FOR_EVIDENCE,),
        inputs={"ticket_closed": context.ticket_closed, "agent_complete": context.agent_complete},
    )


def goodwill_limit(context: RuleContext, rule: InvariantRule) -> RuleEvaluation:
    goodwill = tuple(fact for fact in context.current_facts if fact.kind is EconomicFactKind.GOODWILL and fact.phase in ACTIVE_PHASES)
    total = sum(fact.amount.minor_units for fact in goodwill)
    if total <= context.policy.goodwill_limit:
        return _evaluation(
            context, rule, EvaluationResult.PASS, "GOODWILL_WITHIN_CUMULATIVE_LIMIT",
            facts=goodwill, amounts={"goodwill_value": total, "goodwill_limit": context.policy.goodwill_limit},
            explanation=f"Cumulative goodwill {total} is within limit {context.policy.goodwill_limit}.",
        )
    return _evaluation(
        context, rule, EvaluationResult.FAIL, "CUMULATIVE_GOODWILL_LIMIT_EXCEEDED",
        facts=goodwill,
        amounts={"goodwill_value": total, "goodwill_limit": context.policy.goodwill_limit, "excess": total - context.policy.goodwill_limit},
        explanation="Cumulative goodwill exceeds the trusted policy limit.",
        responses=(ResponseCategory.BLOCK_NEW_ACTION, ResponseCategory.REQUIRE_APPROVAL),
    )


def pending_primary_conflict(context: RuleContext, rule: InvariantRule) -> RuleEvaluation:
    groups: dict[tuple[str, str], list[EconomicFact]] = defaultdict(list)
    for fact in context.current_facts:
        if fact.kind is EconomicFactKind.REFUND and fact.phase in {EconomicPhase.PROPOSED, EconomicPhase.PENDING}:
            groups[(fact.semantic_intent_id, fact.economic_scope)].append(fact)
    conflicts = tuple(fact for group in groups.values() if len(group) > 1 for fact in group)
    if not conflicts:
        return _evaluation(
            context, rule, EvaluationResult.PASS, "NO_EQUIVALENT_PENDING_PRIMARY_CONFLICT",
            explanation="No equivalent unresolved primary refund is duplicated.",
        )
    duplicate_value = sum(item.amount.minor_units for group in groups.values() if len(group) > 1 for item in group[1:])
    return _evaluation(
        context, rule, EvaluationResult.FAIL, "EQUIVALENT_PRIMARY_ALREADY_PENDING",
        facts=conflicts, amounts={"pending_duplicate_value": duplicate_value},
        explanation="An unresolved pending refund has an equivalent new primary action.",
        responses=(ResponseCategory.BLOCK_NEW_ACTION, ResponseCategory.WAIT_FOR_EVIDENCE),
    )


def compensation_reversibility(context: RuleContext, rule: InvariantRule) -> RuleEvaluation:
    candidates = tuple(
        fact for fact in context.current_facts
        if fact.kind is EconomicFactKind.REPLACEMENT and fact.phase in ACTIVE_PHASES
    )
    ineligible = tuple(
        fact for fact in candidates
        if fact.reversible is False or fact.external_state in {"ACCEPTED", "DISPATCHED"}
    )
    if ineligible:
        return _evaluation(
            context, rule, EvaluationResult.WARN, "AUTOMATIC_COMPENSATION_NOT_REVERSIBLE",
            facts=ineligible, explanation="Trusted external state does not permit automatic replacement compensation.",
            responses=(ResponseCategory.REQUIRE_APPROVAL, ResponseCategory.ESCALATE),
        )
    return _evaluation(
        context, rule, EvaluationResult.PASS, "AUTOMATIC_COMPENSATION_REVERSIBILITY_KNOWN",
        facts=candidates, explanation="Any replacement compensation candidate remains reversibly CREATED/RESERVED.",
    )


def currency_consistency(context: RuleContext, rule: InvariantRule) -> RuleEvaluation:
    mismatches = tuple(fact for fact in context.current_facts if fact.amount.currency != context.policy.currency)
    if not mismatches:
        return _evaluation(
            context, rule, EvaluationResult.PASS, "ECONOMIC_CURRENCY_CONSISTENT",
            explanation=f"All facts use pinned currency {context.policy.currency}.",
        )
    return _evaluation(
        context, rule, EvaluationResult.FAIL, "ECONOMIC_CURRENCY_MISMATCH",
        facts=mismatches, explanation="Economic facts contain currency outside the pinned policy.",
        responses=(ResponseCategory.BLOCK_NEW_ACTION, ResponseCategory.ESCALATE),
    )


def settled_primary_immutability(context: RuleContext, rule: InvariantRule) -> RuleEvaluation:
    settled_refunds = tuple(f for f in context.current_facts if f.kind is EconomicFactKind.REFUND and f.phase is EconomicPhase.SETTLED)
    settled_replacements = tuple(f for f in context.current_facts if f.kind is EconomicFactKind.REPLACEMENT and f.phase is EconomicPhase.SETTLED)
    active_refunds = tuple(f for f in context.current_facts if f.kind is EconomicFactKind.REFUND and f.phase in ACTIVE_PHASES)
    active_replacements = tuple(f for f in context.current_facts if f.kind is EconomicFactKind.REPLACEMENT and f.phase in ACTIVE_PHASES)
    conflict = (*settled_refunds, *active_replacements) if settled_refunds and active_replacements else ((*settled_replacements, *active_refunds) if settled_replacements and active_refunds else ())
    if not conflict or context.policy.dual_compensation_exception:
        return _evaluation(
            context, rule, EvaluationResult.PASS, "SETTLED_PRIMARY_PATH_UNCHALLENGED",
            explanation="No competing path challenges the authoritatively settled primary resolution.",
        )
    return _evaluation(
        context, rule, EvaluationResult.FAIL, "SETTLED_PRIMARY_PATH_COMPETED",
        facts=tuple(conflict), explanation="A competing primary resolution exists after exclusive path settlement.",
        responses=(ResponseCategory.BLOCK_NEW_ACTION, ResponseCategory.REQUIRE_APPROVAL, ResponseCategory.ESCALATE),
    )


def commerce_rules(version: str = "1.0.0") -> tuple[InvariantRule, ...]:
    common = {"domain": "commerce", "rule_version": version, "required_fields": ("pact_id", "economic_facts"), "required_evidence": (), "approval_requirement": None}
    return (
        InvariantRule("COMMERCE_REFUND_VALUE_BOUND", description="Refund value cannot exceed capture plus trusted refund exception.", applicable_event_types=("REFUND",), severity=Severity.CRITICAL, evaluation_function=refund_value_bound, allowed_automatic_response=(ResponseCategory.BLOCK_NEW_ACTION,), audit_explanation_template="Compare active refund value to pinned refund bound.", **common),
        InvariantRule("COMMERCE_PRIMARY_RESOLUTION_EXCLUSIVE", description="Refund and replacement are mutually exclusive primary outcomes.", applicable_event_types=("REFUND", "REPLACEMENT"), severity=Severity.CRITICAL, evaluation_function=primary_resolution_exclusive, allowed_automatic_response=(ResponseCategory.BLOCK_NEW_ACTION,), audit_explanation_template="Detect active cross-path overlap.", **common),
        InvariantRule("COMMERCE_DUPLICATE_COMPENSATION", description="Equivalent semantic primary compensation may occur once per approved scope.", applicable_event_types=("REFUND", "REPLACEMENT"), severity=Severity.ERROR, evaluation_function=duplicate_semantic_compensation, allowed_automatic_response=(ResponseCategory.BLOCK_NEW_ACTION,), audit_explanation_template="Group economic objects by semantic intent and scope.", **common),
        InvariantRule("COMMERCE_COMPLETION_REQUIRES_EVIDENCE", description="Completion requires policy-qualified evidence.", applicable_event_types=("CLAIM", "EVIDENCE"), required_evidence=("stripe.refund.succeeded", "carrier.shipment.accepted"), severity=Severity.CRITICAL, evaluation_function=completion_requires_evidence, allowed_automatic_response=(ResponseCategory.WAIT_FOR_EVIDENCE,), audit_explanation_template="Ticket and agent completion are non-authoritative.", **{k:v for k,v in common.items() if k != "required_evidence"}),
        InvariantRule("COMMERCE_GOODWILL_LIMIT", description="Cumulative goodwill remains inside its independent policy limit.", applicable_event_types=("GOODWILL",), severity=Severity.ERROR, evaluation_function=goodwill_limit, allowed_automatic_response=(ResponseCategory.BLOCK_NEW_ACTION,), audit_explanation_template="Sum active goodwill by pact.", **common),
        InvariantRule("COMMERCE_PENDING_PRIMARY_CONFLICT", description="Equivalent primary work cannot duplicate an unresolved pending refund.", applicable_event_types=("REFUND",), severity=Severity.ERROR, evaluation_function=pending_primary_conflict, allowed_automatic_response=(ResponseCategory.BLOCK_NEW_ACTION,), audit_explanation_template="Compare unresolved semantic intent scopes.", **common),
        InvariantRule("COMMERCE_AUTO_COMPENSATION_REQUIRES_REVERSIBILITY", description="Automatic compensation eligibility requires trusted reversible state.", applicable_event_types=("REPLACEMENT",), severity=Severity.WARNING, evaluation_function=compensation_reversibility, allowed_automatic_response=(ResponseCategory.EVALUATE_REGISTERED_COMPENSATION,), audit_explanation_template="Evaluate eligibility only; do not execute.", **common),
        InvariantRule("COMMERCE_CURRENCY_CONSISTENCY", description="All economic facts use the pinned pact currency.", applicable_event_types=("REFUND", "REPLACEMENT", "GOODWILL"), severity=Severity.CRITICAL, evaluation_function=currency_consistency, allowed_automatic_response=(ResponseCategory.BLOCK_NEW_ACTION,), audit_explanation_template="Reject mixed or unsupported currency.", **common),
        InvariantRule("COMMERCE_SETTLED_PRIMARY_PATH_IMMUTABLE", description="A settled exclusive primary path cannot be competed without exception.", applicable_event_types=("REFUND", "REPLACEMENT"), severity=Severity.CRITICAL, evaluation_function=settled_primary_immutability, allowed_automatic_response=(ResponseCategory.BLOCK_NEW_ACTION,), audit_explanation_template="Protect an authoritatively settled primary path.", **common),
    )
