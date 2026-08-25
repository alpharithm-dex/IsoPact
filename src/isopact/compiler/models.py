from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SubjectReference(StrictModel):
    subject_type: str = Field(min_length=1, max_length=40)
    value: str = Field(min_length=1, max_length=120)
    source: Literal["customer_request", "ticket_context", "known_context"]
    source_excerpt: str = Field(min_length=1, max_length=300)


class SourceGrounding(StrictModel):
    field_name: str = Field(min_length=1, max_length=80)
    source: Literal["customer_request", "ticket_context", "known_context"]
    source_excerpt: str = Field(min_length=1, max_length=300)


class ExtractedAmount(StrictModel):
    amount_text: str = Field(min_length=1, max_length=40)
    currency: str = Field(min_length=3, max_length=3)
    minor_units: int = Field(ge=0)
    source: Literal["customer_request", "ticket_context", "known_context"]

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class CandidateOutcomePact(StrictModel):
    """Untrusted structured model output. Deliberately contains no policy authority."""

    candidate_outcome_type: str = Field(min_length=1, max_length=80)
    subject_references: tuple[SubjectReference, ...]
    requested_resolution_semantics: str = Field(min_length=1, max_length=200)
    candidate_resolution_paths: tuple[str, ...]
    exclusive_resolution_suspected: bool
    candidate_evidence_requirements: tuple[str, ...]
    explicit_user_constraints: tuple[str, ...]
    ambiguities: tuple[str, ...]
    source_grounding: tuple[SourceGrounding, ...]
    extracted_amount: ExtractedAmount | None = None


class ProviderMetadata(StrictModel):
    provider: str
    model: str
    execution_mode: Literal["LIVE", "FIXTURE"]
    latency_ms: int | None = Field(default=None, ge=0)


class CandidateCompilation(StrictModel):
    candidate: CandidateOutcomePact
    metadata: ProviderMetadata


class AuthoritativeOrder(StrictModel):
    order_id: str
    customer_id: str
    captured_minor_units: int = Field(ge=0)
    currency: str

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class AuthoritativeCaseContext(StrictModel):
    tenant: str
    domain: str
    case_type: str
    ticket_id: str
    orders: tuple[AuthoritativeOrder, ...]


class TrustedPolicy(StrictModel):
    policy_id: str
    version: str
    allowed_outcome_type: str
    allowed_candidate_concepts: frozenset[str]
    resolution_path_mapping: dict[str, str]
    allowed_resolution_paths: frozenset[str]
    exclusive_slot: str
    goodwill_limit_minor_units: int
    goodwill_currency: str
    completion_evidence: dict[str, tuple[str, ...]]
    evidence_max_rank: dict[str, int]
    human_approval_threshold_minor_units: int
    duplicate_compensation_blocked: bool
    evaluation_rule_set_id: str = "commerce_missing_order_rules"
    evaluation_rule_set_version: str = "1"


class ValidationStatus(StrEnum):
    VALID = "VALID"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    REJECTED = "REJECTED"


class DeterministicContribution(StrictModel):
    verified_subjects: dict[str, str]
    selected_policy_id: str | None
    selected_policy_version: str | None
    assigned_resolution_paths: tuple[str, ...]
    assigned_exclusive_slot: str | None
    assigned_goodwill_limit_minor_units: int | None
    assigned_goodwill_currency: str | None
    assigned_evidence_requirements: dict[str, tuple[str, ...]]
    assigned_approval_threshold_minor_units: int | None
    reason_codes: tuple[str, ...]


class ValidatedOutcomePactDraft(StrictModel):
    draft_id: str
    outcome_type: str
    subjects: dict[str, str]
    requested_resolution_semantics: str
    allowed_resolution_paths: tuple[str, ...]
    exclusive_slot: str
    goodwill_limit_minor_units: int
    goodwill_currency: str
    completion_evidence: dict[str, tuple[str, ...]]
    human_approval_threshold_minor_units: int
    duplicate_compensation_blocked: bool
    policy_id: str
    policy_version: str
    activation_state: Literal["DRAFT_NOT_ENFORCEABLE"] = "DRAFT_NOT_ENFORCEABLE"


class ValidationResult(StrictModel):
    status: ValidationStatus
    deterministic_contribution: DeterministicContribution
    trusted_draft: ValidatedOutcomePactDraft | None


class CompilationResult(StrictModel):
    model_contribution: CandidateCompilation | None
    deterministic_result: ValidationResult
    provider_error: str | None = None
