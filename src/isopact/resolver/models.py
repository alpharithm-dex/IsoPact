from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from isopact.domain.models import Money


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AuthorityTier(StrEnum):
    AUTOMATIC = "AUTOMATIC"
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"
    HUMAN_REVIEW_ONLY = "HUMAN_REVIEW_ONLY"


class PlanValidationStatus(StrEnum):
    VALID_AUTOMATIC = "VALID_AUTOMATIC"
    VALID_REQUIRES_APPROVAL = "VALID_REQUIRES_APPROVAL"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    REJECTED = "REJECTED"


class CompensationExecutionState(StrEnum):
    PLANNED = "PLANNED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    AUTHORIZED = "AUTHORIZED"
    EXECUTING = "EXECUTING"
    CONFIRMED = "CONFIRMED"
    FAILED_AUTHORITATIVELY = "FAILED_AUTHORITATIVELY"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"
    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    REJECTED = "REJECTED"


class ExecutionDecision(StrEnum):
    EXECUTE = "EXECUTE"
    DEFER = "DEFER"
    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    REJECTED = "REJECTED"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class CompensationDefinition:
    compensation_id: str
    registry_version: str
    domain: str
    forward_action_type: str
    compensation_action_type: str | None
    target_system: str
    eligible_source_states: tuple[str, ...]
    forbidden_source_states: tuple[str, ...]
    required_preconditions: tuple[str, ...]
    authority_tier: AuthorityTier
    approval_requirement: str | None
    parameter_binding_strategy: str
    required_evidence_after_execution: tuple[str, ...]
    idempotency_scope: str
    economic_effect_category: str
    description: str
    mandatory_order: int

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["authority_tier"] = self.authority_tier.value
        return data


class ResolverCandidate(StrictModel):
    registry_action_id: str
    authority_tier: AuthorityTier
    approval_requirement: str | None
    target_system: str
    eligible_source_states: tuple[str, ...]
    description: str


class ResolverContext(StrictModel):
    pact_id: str
    pact_outcome: str
    selected_primary_resolution: str
    conflict_ids: tuple[str, ...]
    conflict_summaries: tuple[str, ...]
    economic_position: dict[str, int | str | list[str]]
    reversible_external_states: dict[str, str]
    targets_by_registry_action: dict[str, str]
    available_candidates: tuple[ResolverCandidate, ...]
    relevant_evidence_summaries: tuple[str, ...]
    untrusted_enterprise_text: str = ""


class CandidateResolutionPlan(StrictModel):
    pact_id: str
    conflict_ids: tuple[str, ...]
    selected_registry_action_ids: tuple[str, ...]
    ordered_action_preferences: tuple[str, ...]
    reasoning_summary: str = Field(min_length=1, max_length=1000)
    expected_resolution_effect: str = Field(min_length=1, max_length=500)
    conditions_or_uncertainties: tuple[str, ...]
    requires_human_attention: bool


class ResolverMetadata(StrictModel):
    provider: str
    model: str
    execution_mode: Literal["LIVE", "FIXTURE"]
    latency_ms: int = Field(ge=0)


class ResolutionProposal(StrictModel):
    candidate: CandidateResolutionPlan
    metadata: ResolverMetadata


@dataclass(frozen=True, slots=True)
class GraphTarget:
    target_id: str
    target_system: str
    forward_action_type: str
    current_state: str
    pact_id: str
    economic_object_id: str | None
    amount: Money | None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["amount"] = asdict(self.amount) if self.amount else None
        return data


@dataclass(frozen=True, slots=True)
class BoundCompensationAction:
    ordinal: int
    registry_action_id: str
    registry_version: str
    compensation_action_type: str | None
    target_system: str
    target_id: str
    forward_action_type: str
    authority_tier: AuthorityTier
    approval_requirement: str | None
    planned_against_state: str
    validated_against_state: str
    semantic_operation_key: str
    required_evidence_after_execution: tuple[str, ...]
    economic_effect_category: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["authority_tier"] = self.authority_tier.value
        return data


@dataclass(frozen=True, slots=True)
class ValidatedResolutionPlan:
    plan_id: str
    pact_id: str
    conflict_ids: tuple[str, ...]
    status: PlanValidationStatus
    actions: tuple[BoundCompensationAction, ...]
    reason_codes: tuple[str, ...]
    policy_version: str
    registry_version: str
    proposed_by: str
    model: str
    model_contribution: dict[str, Any]
    created_at: str
    validator_model_calls: int = 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["actions"] = [item.to_dict() for item in self.actions]
        return data


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    approval_id: str
    pact_id: str
    resolution_plan_id: str
    compensation_execution_id: str
    registry_action_id: str
    registry_version: str
    requested_action: str
    target: str
    economic_impact: Money
    reason: str
    required_authority: str
    policy_version: str
    requested_at: str
    status: ApprovalStatus
    decided_by: str | None = None
    decision: str | None = None
    decision_timestamp: str | None = None
    decision_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["economic_impact"] = asdict(self.economic_impact)
        data["status"] = self.status.value
        return data


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    approval_decision_id: str
    approval_id: str
    pact_id: str
    resolution_plan_id: str
    compensation_execution_id: str
    registry_action_id: str
    registry_version: str
    target: str
    policy_version: str
    approved: bool
    decided_by: str
    decided_at: str
    reason: str

    def to_dict(self) -> dict[str, Any]: return asdict(self)


@dataclass(frozen=True, slots=True)
class CompensationExecution:
    execution_id: str
    pact_id: str
    conflict_ids: tuple[str, ...]
    plan_id: str
    registry_action_id: str
    registry_version: str
    target_system: str
    target_id: str
    semantic_operation_key: str
    state: CompensationExecutionState
    authority_tier: AuthorityTier
    approval_id: str | None
    planned_against_state: str
    validated_against_state: str
    executed_against_state: str | None
    precondition_result: str | None
    external_call_executed: bool
    evidence_ids: tuple[str, ...]
    economic_effect_category: str
    trace_id: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        data["authority_tier"] = self.authority_tier.value
        return data


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    decision: ExecutionDecision
    execution: CompensationExecution
    external_result: dict[str, Any] | None = None
