from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class AgentRole(StrEnum):
    SUPPORT = "SUPPORT"
    FULFILLMENT = "FULFILLMENT"
    RETENTION = "RETENTION"
    RESOLVER = "RESOLVER"


class Capability(StrEnum):
    READ_PACT = "READ_PACT"
    READ_TICKET = "READ_TICKET"
    READ_ORDER = "READ_ORDER"
    READ_FULFILLMENT = "READ_FULFILLMENT"
    READ_CUSTOMER = "READ_CUSTOMER"
    REQUEST_REFUND = "REQUEST_REFUND"
    REQUEST_REPLACEMENT = "REQUEST_REPLACEMENT"
    REQUEST_GOODWILL = "REQUEST_GOODWILL"
    UPDATE_TICKET = "UPDATE_TICKET"
    READ_CONFLICTS = "READ_CONFLICTS"
    REQUEST_VALIDATED_PLAN = "REQUEST_VALIDATED_PLAN"
    SUBMIT_VALIDATED_PLAN = "SUBMIT_VALIDATED_PLAN"
    READ_APPROVAL = "READ_APPROVAL"


CAPABILITY_MATRIX: dict[AgentRole, frozenset[Capability]] = {
    AgentRole.SUPPORT: frozenset({Capability.READ_PACT, Capability.READ_TICKET, Capability.READ_ORDER, Capability.REQUEST_REFUND, Capability.UPDATE_TICKET}),
    AgentRole.FULFILLMENT: frozenset({Capability.READ_PACT, Capability.READ_ORDER, Capability.READ_FULFILLMENT, Capability.REQUEST_REPLACEMENT}),
    AgentRole.RETENTION: frozenset({Capability.READ_PACT, Capability.READ_CUSTOMER, Capability.REQUEST_GOODWILL}),
    AgentRole.RESOLVER: frozenset({Capability.READ_PACT, Capability.READ_CONFLICTS, Capability.REQUEST_VALIDATED_PLAN, Capability.SUBMIT_VALIDATED_PLAN, Capability.READ_APPROVAL}),
}


@dataclass(frozen=True, slots=True)
class AgentIdentity:
    agent_id: str
    role: AgentRole
    display_name: str
    skill_id: str
    google_agent_resource: str | None = None
    google_managed_identity: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self); data["role"] = self.role.value; return data


@dataclass(frozen=True, slots=True)
class AgentSessionContext:
    pact_id: str
    agent_identity: AgentIdentity
    session_id: str
    trace_id: str


@dataclass(frozen=True, slots=True)
class AgentToolTrace:
    pact_id: str
    agent_id: str
    google_agent_resource: str | None
    agent_role: str
    session_id: str
    a2a_interaction_id: str | None
    tool_call: str
    gateway_decision: str | None
    operation_identity: str | None
    evidence_ids: tuple[str, ...]
    rule_evaluation_ids: tuple[str, ...]
    compensation_execution_ids: tuple[str, ...]
    settlement_status: str
    trace_id: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("evidence_ids", "rule_evaluation_ids", "compensation_execution_ids"): data[key] = list(data[key])
        return data
