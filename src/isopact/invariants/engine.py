from __future__ import annotations

from isopact.domain.models import Money
from isopact.evidence.identity import stable_id
from isopact.evidence.models import PactLifecycle

from .economics import EconomicReducer
from .models import (
    ConflictRecord,
    EconomicFact,
    EconomicPhase,
    EconomicPolicy,
    EvaluationBundle,
    EvaluationResult,
    ProtectionEvent,
    ResponseCategory,
    RuleContext,
    RuleSet,
)
from .rules import commerce_rules
from isopact.observability import telemetry
from time import perf_counter


class RuleCatalog:
    def __init__(self) -> None:
        self._sets: dict[tuple[str, str], RuleSet] = {}

    def register(self, rule_set: RuleSet) -> None:
        key = (rule_set.rule_set_id, rule_set.version)
        if key in self._sets:
            raise ValueError("referenced rule sets are immutable")
        self._sets[key] = rule_set

    def resolve(self, rule_set_id: str, version: str) -> RuleSet:
        try:
            return self._sets[(rule_set_id, version)]
        except KeyError as exc:
            raise ValueError(f"unknown pinned rule set {rule_set_id}@{version}") from exc


def default_rule_catalog() -> RuleCatalog:
    catalog = RuleCatalog()
    catalog.register(RuleSet("commerce_missing_order_rules", "1", commerce_rules("1.0.0")))
    catalog.register(RuleSet("commerce_missing_order_rules", "2", commerce_rules("2.0.0")))
    return catalog


def synthesize_lifecycle(context: RuleContext, evaluations) -> PactLifecycle:
    failures = [item for item in evaluations if item.result is EvaluationResult.FAIL]
    if failures:
        conflicting_ops = {op for item in failures for op in item.conflicting_operation_ids}
        existing_effect = any(
            fact.executed
            and fact.phase is not EconomicPhase.BLOCKED
            and (not conflicting_ops or fact.operation_identity in conflicting_ops)
            for fact in context.current_facts
        )
        return PactLifecycle.VIOLATED if existing_effect else PactLifecycle.AT_RISK
    if context.approval_outstanding:
        return PactLifecycle.ESCALATED
    if any(item.result is EvaluationResult.WARN and ResponseCategory.REQUIRE_APPROVAL in item.permitted_response_categories for item in evaluations):
        return PactLifecycle.ESCALATED
    if any(item.result is EvaluationResult.UNKNOWN for item in evaluations):
        if any(fact.phase in {EconomicPhase.PROPOSED, EconomicPhase.PENDING} for fact in context.current_facts):
            return PactLifecycle.PENDING
        return PactLifecycle.OPEN
    if context.settlement_evidence_satisfied and context.selected_resolution:
        return PactLifecycle.SETTLED
    if any(fact.phase in {EconomicPhase.PROPOSED, EconomicPhase.PENDING} for fact in context.current_facts):
        return PactLifecycle.PENDING
    return PactLifecycle.OPEN


class CommerceInvariantEngine:
    def __init__(self, catalog: RuleCatalog | None = None) -> None:
        self.catalog = catalog or default_rule_catalog()
        self.model_calls = 0

    def evaluate(
        self,
        *,
        pact_id: str,
        graph_revision: int,
        facts: tuple[EconomicFact, ...],
        policy: EconomicPolicy,
        selected_resolution: str | None,
        settlement_evidence_satisfied: bool,
        ticket_closed: bool,
        agent_complete: bool,
        protection_events: tuple[ProtectionEvent, ...] = (),
        approval_outstanding: bool = False,
        evaluated_at: str,
    ) -> EvaluationBundle:
        started = perf_counter()
        with telemetry.span("isopact.invariants.evaluate", **{"isopact.pact_id": pact_id, "isopact.rule.id": policy.evaluation_rule_set_id, "isopact.rule.version": policy.evaluation_rule_set_version}):
            result = self._evaluate(pact_id=pact_id, graph_revision=graph_revision, facts=facts, policy=policy, selected_resolution=selected_resolution, settlement_evidence_satisfied=settlement_evidence_satisfied, ticket_closed=ticket_closed, agent_complete=agent_complete, protection_events=protection_events, approval_outstanding=approval_outstanding, evaluated_at=evaluated_at)
            for item in result.evaluations:
                if item.result is EvaluationResult.FAIL:
                    telemetry.log(
                        "WARNING",
                        "invariant evaluation failed",
                        **{
                            "isopact.pact_id": pact_id,
                            "isopact.rule.id": item.rule_id,
                            "isopact.rule.version": item.rule_version,
                        },
                    )
        telemetry.observe("isopact.invariants.duration", (perf_counter() - started) * 1000, rule_id=policy.evaluation_rule_set_id)
        for item in result.evaluations:
            if item.result is EvaluationResult.FAIL:
                telemetry.add("isopact.invariant.failures", rule_id=item.rule_id)
        return result

    def _evaluate(self, *, pact_id: str, graph_revision: int, facts: tuple[EconomicFact, ...], policy: EconomicPolicy, selected_resolution: str | None, settlement_evidence_satisfied: bool, ticket_closed: bool, agent_complete: bool, protection_events: tuple[ProtectionEvent, ...], approval_outstanding: bool, evaluated_at: str) -> EvaluationBundle:
        rule_set = self.catalog.resolve(
            policy.evaluation_rule_set_id, policy.evaluation_rule_set_version
        )
        position, current_facts, protection_summary = EconomicReducer.reduce(
            facts, policy, protection_events
        )
        context = RuleContext(
            pact_id=pact_id,
            graph_revision=graph_revision,
            facts=facts,
            current_facts=current_facts,
            position=position,
            policy=policy,
            selected_resolution=selected_resolution,
            settlement_evidence_satisfied=settlement_evidence_satisfied,
            ticket_closed=ticket_closed,
            agent_complete=agent_complete,
            approval_outstanding=approval_outstanding,
        )
        evaluations = tuple(rule.evaluate(context) for rule in rule_set.rules)
        lifecycle = synthesize_lifecycle(context, evaluations)
        conflicts = tuple(
            self._conflict(context, evaluation, evaluated_at)
            for evaluation in evaluations
            if evaluation.result is EvaluationResult.FAIL
        )
        return EvaluationBundle(
            pact_id=pact_id,
            graph_revision=graph_revision,
            rule_set_id=rule_set.rule_set_id,
            rule_set_version=rule_set.version,
            authorization_policy_version=policy.authorization_policy_reference,
            current_policy_version=f"{policy.policy_id}@{policy.current_policy_version}",
            economic_position=position,
            protection_summary=protection_summary,
            evaluations=evaluations,
            conflicts=conflicts,
            lifecycle_recommendation=lifecycle,
            evaluated_at=evaluated_at,
            model_calls=self.model_calls,
        )

    @staticmethod
    def _conflict(context: RuleContext, evaluation, evaluated_at: str) -> ConflictRecord:
        impact = max(evaluation.economic_amounts.get("excess", 0), evaluation.economic_amounts.get("overlap", 0), evaluation.economic_amounts.get("duplicate_value", 0), evaluation.economic_amounts.get("pending_duplicate_value", 0))
        conflict_id = stable_id(
            "conflict",
            {
                "pact_id": context.pact_id,
                "rule_id": evaluation.rule_id,
                "rule_version": evaluation.rule_version,
                "operations": evaluation.conflicting_operation_ids,
            },
        )
        return ConflictRecord(
            conflict_id=conflict_id,
            pact_id=context.pact_id,
            rule_id=evaluation.rule_id,
            rule_version=evaluation.rule_version,
            severity=evaluation.severity,
            status="OPEN",
            economic_impact=Money(context.policy.currency, impact),
            related_operation_ids=evaluation.conflicting_operation_ids,
            related_evidence_ids=evaluation.evidence_ids,
            first_detected_at=evaluated_at,
            last_evaluated_at=evaluated_at,
            resolution_eligibility=(
                "REGISTERED_COMPENSATION_CANDIDATE"
                if ResponseCategory.EVALUATE_REGISTERED_COMPENSATION in evaluation.permitted_response_categories
                else "NO_AUTOMATIC_RESOLUTION"
            ),
            human_approval_requirement=(
                "REQUIRED"
                if ResponseCategory.REQUIRE_APPROVAL in evaluation.permitted_response_categories
                else None
            ),
        )
