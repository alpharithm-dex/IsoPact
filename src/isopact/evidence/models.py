from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import IntEnum, StrEnum
from typing import Any


class EvidenceRank(IntEnum):
    AUTHORITATIVE_SETTLED_EVENT = 1
    VERIFIED_SYSTEM_QUERY = 2
    ACCEPTED_PENDING_RESPONSE = 3
    AGENT_INTERPRETATION = 4
    UNVERIFIED_NATURAL_LANGUAGE = 5


class PactLifecycle(StrEnum):
    OPEN = "OPEN"
    PENDING = "PENDING"
    AT_RISK = "AT_RISK"
    VIOLATED = "VIOLATED"
    ESCALATED = "ESCALATED"
    SETTLED = "SETTLED"


class ImmediateState(StrEnum):
    ACCEPTED = "ACCEPTED"
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    REVERSED = "REVERSED"
    CLOSED = "CLOSED"
    COMPLETE = "COMPLETE"
    UNKNOWN = "UNKNOWN"


class ClaimType(StrEnum):
    GATEWAY_AUTHORIZATION = "GATEWAY_AUTHORIZATION"
    API_RESPONSE = "API_RESPONSE"
    SYSTEM_STATE = "SYSTEM_STATE"
    AGENT_ASSERTION = "AGENT_ASSERTION"
    AUTHORITATIVE_EVENT = "AUTHORITATIVE_EVENT"
    VERIFIED_QUERY = "VERIFIED_QUERY"


class Authenticity(StrEnum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True, slots=True)
class Participant:
    participant_id: str
    pact_id: str
    kind: str
    display_name: str
    authenticated_principal: str
    roles: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["roles"] = list(self.roles)
        return data


@dataclass(frozen=True, slots=True)
class StateClaim:
    claim_id: str
    pact_id: str
    claim_type: ClaimType
    source_system: str
    source_actor: str | None
    subject: str
    external_object_id: str | None
    operation_identity: str | None
    resolution_path: str | None
    immediate_state: ImmediateState
    evidence_rank: EvidenceRank
    occurred_at: str
    ingested_at: str
    trace_id: str
    source_event_id: str | None = None
    references: tuple[str, ...] = ()
    sequence: int = 0
    claim_schema_version: str = "isopact.stateclaim.v1"
    previous_claim_hash: str = ""
    claim_hash: str = ""
    agent_identity: str | None = None
    policy_references: tuple[str, ...] = ()
    rule_references: tuple[str, ...] = ()
    normalized_payload: dict[str, Any] = field(default_factory=dict)
    normalized_payload_hash: str = ""
    protected_references: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["claim_type"] = self.claim_type.value
        data["immediate_state"] = self.immediate_state.value
        data["evidence_rank"] = int(self.evidence_rank)
        data["references"] = list(self.references)
        data["sequence_number"] = data.pop("sequence")
        data["policy_references"] = list(self.policy_references)
        data["rule_references"] = list(self.rule_references)
        data["protected_references"] = list(self.protected_references)
        return data


@dataclass(frozen=True, slots=True)
class EvidenceDelivery:
    delivery_id: str
    delivery_mechanism: str
    pubsub_message_id: str | None
    publish_timestamp: str | None
    received_at: str
    attributes: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Evidence:
    evidence_id: str
    pact_id: str
    source_system: str
    source_event_id: str
    evidence_type: str
    evidence_rank: EvidenceRank
    authenticity: Authenticity
    subject: str
    external_object_id: str | None
    operation_identity: str | None
    operation_attempt: int
    source_sequence: int | None
    resolution_path: str
    resolved_state: ImmediateState
    payload_hash: str
    occurred_at: str
    ingested_at: str
    verification_mechanism: str
    trace_id: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_rank"] = int(self.evidence_rank)
        data["authenticity"] = self.authenticity.value
        data["resolved_state"] = self.resolved_state.value
        return data


@dataclass(frozen=True, slots=True)
class EconomicEvent:
    event_id: str
    pact_id: str
    source_event_id: str
    kind: str
    phase: str
    amount_minor_units: int | None
    currency: str | None
    subject: str
    operation_identity: str | None
    evidence_ids: tuple[str, ...]
    occurred_at: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_ids"] = list(self.evidence_ids)
        return data


@dataclass(frozen=True, slots=True)
class Conflict:
    conflict_id: str
    pact_id: str
    kind: str
    status: str
    evidence_ids: tuple[str, ...]
    detected_at: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_ids"] = list(self.evidence_ids)
        return data


@dataclass(frozen=True, slots=True)
class SettlementEvaluation:
    evaluation_id: str
    pact_id: str
    input_revision: int
    selected_resolution: str | None
    required_evidence: tuple[str, ...]
    qualifying_evidence_ids: tuple[str, ...]
    result: PactLifecycle
    reason_codes: tuple[str, ...]
    evaluated_at: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["required_evidence"] = list(self.required_evidence)
        data["qualifying_evidence_ids"] = list(self.qualifying_evidence_ids)
        data["result"] = self.result.value
        data["reason_codes"] = list(self.reason_codes)
        return data


@dataclass(frozen=True, slots=True)
class SettlementProof:
    proof_id: str
    pact_id: str
    selected_resolution: str
    settlement_status: PactLifecycle
    authoritative_evidence_ids: tuple[str, ...]
    final_external_states: dict[str, str]
    policy_id: str
    policy_version: str
    settlement_timestamp: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["settlement_status"] = self.settlement_status.value
        data["authoritative_evidence_ids"] = list(self.authoritative_evidence_ids)
        return data


@dataclass(frozen=True, slots=True)
class IngestionResult:
    evidence_id: str
    logical_evidence_created: bool
    transport_record_created: bool
    economic_event_created: bool
    state_claim_created: bool
    settlement_transition_created: bool
    reservation_reconciled: bool
    pact_state: PactLifecycle
    resolved_external_state: ImmediateState | None
    graph_revision: int


@dataclass(frozen=True, slots=True)
class PactGraphSnapshot:
    pact_id: str
    state: PactLifecycle
    selected_resolution: str | None
    revision: int
    settlement_transition_count: int
    resolved_operations: dict[str, dict[str, Any]]
    claim_count: int
    evidence_count: int
    economic_event_count: int
    delivery_count: int
    participant_count: int
    conflict_count: int
    evaluation_count: int
    settlement_proof_count: int
