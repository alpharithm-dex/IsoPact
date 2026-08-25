from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Callable

from isopact.domain.models import Money
from isopact.evidence.models import PactLifecycle


class EvaluationResult(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ResponseCategory(StrEnum):
    NONE = "NONE"
    WAIT_FOR_EVIDENCE = "WAIT_FOR_EVIDENCE"
    BLOCK_NEW_ACTION = "BLOCK_NEW_ACTION"
    EVALUATE_REGISTERED_COMPENSATION = "EVALUATE_REGISTERED_COMPENSATION"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    ESCALATE = "ESCALATE"


class EconomicFactKind(StrEnum):
    REFUND = "REFUND"
    REPLACEMENT = "REPLACEMENT"
    GOODWILL = "GOODWILL"
    OTHER_EXCEPTION = "OTHER_EXCEPTION"


class EconomicPhase(StrEnum):
    PROPOSED = "PROPOSED"
    PENDING = "PENDING"
    SETTLED = "SETTLED"
    FAILED = "FAILED"
    REVERSED = "REVERSED"
    BLOCKED = "BLOCKED"


class ProtectionEventType(StrEnum):
    INVALID_ACTION_PREVENTED = "INVALID_ACTION_PREVENTED"
    AUTHORIZED_VALUE_RECOVERED = "AUTHORIZED_VALUE_RECOVERED"
    LEGITIMATE_VALUE_DELAYED = "LEGITIMATE_VALUE_DELAYED"


@dataclass(frozen=True, slots=True)
class EconomicPolicy:
    policy_id: str
    authorization_policy_version: str
    evaluation_rule_set_id: str
    evaluation_rule_set_version: str
    current_policy_version: str
    currency: str
    captured_value: int
    goodwill_limit: int
    authorized_refund_exception: int = 0
    dual_compensation_exception: bool = False
    partial_refunds_allowed: bool = True

    def __post_init__(self) -> None:
        currency = self.currency.strip().upper()
        if currency != "USD":
            raise ValueError("Stage 6 commerce policy supports USD only")
        for name in ("captured_value", "goodwill_limit", "authorized_refund_exception"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        object.__setattr__(self, "currency", currency)

    @property
    def authorization_policy_reference(self) -> str:
        return f"{self.policy_id}@{self.authorization_policy_version}"

    @property
    def evaluation_policy_reference(self) -> str:
        return f"{self.evaluation_rule_set_id}@{self.evaluation_rule_set_version}"


@dataclass(frozen=True, slots=True)
class EconomicFact:
    fact_id: str
    economic_object_id: str
    semantic_intent_id: str
    economic_scope: str
    kind: EconomicFactKind
    phase: EconomicPhase
    amount: Money
    subject_id: str
    operation_identity: str | None
    external_object_id: str | None
    source_system: str
    source_version: int
    occurred_at: str
    executed: bool
    authorized: bool
    external_state: str | None = None
    related_evidence_ids: tuple[str, ...] = ()
    reversible: bool | None = None
    preexisting_outside_gateway: bool = False

    def __post_init__(self) -> None:
        if not self.fact_id or not self.economic_object_id or not self.semantic_intent_id:
            raise ValueError("fact, economic object, and semantic intent IDs are required")
        if self.source_version < 0:
            raise ValueError("source_version must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["kind"] = self.kind.value
        data["phase"] = self.phase.value
        data["amount"] = asdict(self.amount)
        data["related_evidence_ids"] = list(self.related_evidence_ids)
        return data


@dataclass(frozen=True, slots=True)
class EconomicPosition:
    currency: str
    captured_value: int
    authorized_primary_value: int
    pending_primary_value: int
    settled_primary_value: int
    failed_primary_value: int
    replacement_projected_value: int
    replacement_committed_value: int
    goodwill_authorized_value: int
    goodwill_settled_value: int
    other_exception_value: int
    blocked_value: int
    recovered_value: int
    legitimately_delayed_value: int
    projected_total_compensation: int
    settled_total_compensation: int
    projected_excess_exposure: int
    settled_excess_exposure: int
    protected_value: int
    recoverable_candidate_value: int
    provenance: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["provenance"] = list(self.provenance)
        return data


@dataclass(frozen=True, slots=True)
class ProtectionEvent:
    protection_event_id: str
    event_type: ProtectionEventType
    economic_object_id: str
    operation_identity: str | None
    amount: Money
    reason_code: str
    related_fact_ids: tuple[str, ...]
    occurred_at: str
    related_conflict_ids: tuple[str, ...] = ()
    compensation_execution_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["event_type"] = self.event_type.value
        data["amount"] = asdict(self.amount)
        data["related_fact_ids"] = list(self.related_fact_ids)
        data["related_conflict_ids"] = list(self.related_conflict_ids)
        data["compensation_execution_ids"] = list(self.compensation_execution_ids)
        data["evidence_ids"] = list(self.evidence_ids)
        return data


@dataclass(frozen=True, slots=True)
class ProtectionSummary:
    currency: str
    invalid_actions_prevented: int
    authorized_value_recovered: int
    legitimate_value_delayed: int
    protected_value: int
    unique_event_count: int
    event_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["event_ids"] = list(self.event_ids)
        return data


@dataclass(frozen=True, slots=True)
class RuleContext:
    pact_id: str
    graph_revision: int
    facts: tuple[EconomicFact, ...]
    current_facts: tuple[EconomicFact, ...]
    position: EconomicPosition
    policy: EconomicPolicy
    selected_resolution: str | None
    settlement_evidence_satisfied: bool
    ticket_closed: bool
    agent_complete: bool
    approval_outstanding: bool = False


@dataclass(frozen=True, slots=True)
class RuleEvaluation:
    evaluation_id: str
    pact_id: str
    rule_id: str
    rule_version: str
    result: EvaluationResult
    severity: Severity
    reason_code: str
    input_facts: dict[str, Any]
    evidence_ids: tuple[str, ...]
    economic_amounts: dict[str, int]
    conflicting_operation_ids: tuple[str, ...]
    explanation: str
    permitted_response_categories: tuple[ResponseCategory, ...]
    authorization_policy_version: str
    evaluation_policy_version: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["result"] = self.result.value
        data["severity"] = self.severity.value
        data["evidence_ids"] = list(self.evidence_ids)
        data["conflicting_operation_ids"] = list(self.conflicting_operation_ids)
        data["permitted_response_categories"] = [x.value for x in self.permitted_response_categories]
        return data


RuleFunction = Callable[[RuleContext, "InvariantRule"], RuleEvaluation]


@dataclass(frozen=True, slots=True)
class InvariantRule:
    rule_id: str
    rule_version: str
    domain: str
    description: str
    applicable_event_types: tuple[str, ...]
    required_fields: tuple[str, ...]
    required_evidence: tuple[str, ...]
    severity: Severity
    evaluation_function: RuleFunction = field(repr=False, compare=False)
    allowed_automatic_response: tuple[ResponseCategory, ...] = ()
    approval_requirement: str | None = None
    audit_explanation_template: str = ""

    def evaluate(self, context: RuleContext) -> RuleEvaluation:
        return self.evaluation_function(context, self)


@dataclass(frozen=True, slots=True)
class RuleSet:
    rule_set_id: str
    version: str
    rules: tuple[InvariantRule, ...]


@dataclass(frozen=True, slots=True)
class ConflictRecord:
    conflict_id: str
    pact_id: str
    rule_id: str
    rule_version: str
    severity: Severity
    status: str
    economic_impact: Money
    related_operation_ids: tuple[str, ...]
    related_evidence_ids: tuple[str, ...]
    first_detected_at: str
    last_evaluated_at: str
    resolution_eligibility: str
    human_approval_requirement: str | None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.value
        data["economic_impact"] = asdict(self.economic_impact)
        data["related_operation_ids"] = list(self.related_operation_ids)
        data["related_evidence_ids"] = list(self.related_evidence_ids)
        return data


@dataclass(frozen=True, slots=True)
class EvaluationBundle:
    pact_id: str
    graph_revision: int
    rule_set_id: str
    rule_set_version: str
    authorization_policy_version: str
    current_policy_version: str
    economic_position: EconomicPosition
    protection_summary: ProtectionSummary
    evaluations: tuple[RuleEvaluation, ...]
    conflicts: tuple[ConflictRecord, ...]
    lifecycle_recommendation: PactLifecycle
    evaluated_at: str
    model_calls: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "pact_id": self.pact_id,
            "graph_revision": self.graph_revision,
            "rule_set_id": self.rule_set_id,
            "rule_set_version": self.rule_set_version,
            "authorization_policy_version": self.authorization_policy_version,
            "current_policy_version": self.current_policy_version,
            "economic_position": self.economic_position.to_dict(),
            "protection_summary": self.protection_summary.to_dict(),
            "evaluations": [item.to_dict() for item in self.evaluations],
            "conflicts": [item.to_dict() for item in self.conflicts],
            "lifecycle_recommendation": self.lifecycle_recommendation.value,
            "evaluated_at": self.evaluated_at,
            "model_calls": self.model_calls,
        }
