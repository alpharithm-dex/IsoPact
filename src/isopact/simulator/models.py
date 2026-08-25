from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class EconomicPhase(StrEnum):
    PROJECTED = "PROJECTED"
    PENDING = "PENDING"
    SETTLED = "SETTLED"
    FAILED = "FAILED"
    REVERSED = "REVERSED"


@dataclass(frozen=True, slots=True)
class ScheduledAction:
    action_id: str
    logical_time: int
    actor: str
    target_system: str
    tool: str
    inputs: dict[str, Any]
    enforcement_boundary: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class InterceptionDecision:
    decision: str
    reason_code: str
    pact_id: str | None = None
    actor: str | None = None
    action_id: str | None = None
    target_system: str | None = None
    tool: str | None = None
    operation_identity: str | None = None
    resolution_slot: str | None = None
    policy_id: str | None = None
    policy_version: str | None = None
    reservation_state_before: str | None = None
    external_call_executed: bool = False
    reservation_state_after: str | None = None
    trace_id: str | None = None


@dataclass(slots=True)
class ActionResult:
    action_id: str
    logical_time: int
    actor: str
    target_system: str
    tool: str
    inputs: dict[str, Any]
    interceptor_decision: dict[str, Any]
    external_call_executed: bool
    external_object_id: str | None
    immediate_result: dict[str, Any]
    scheduled_follow_up_events: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EconomicEvent:
    event_id: str
    logical_timestamp: int
    source_system: str
    event_type: str
    phase: EconomicPhase
    subject_id: str
    external_object_id: str
    amount_minor_units: int | None = None
    currency: str | None = None
    resource: str | None = None
    actor: str | None = None
    session_id: str | None = None
    authorized_exception: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["phase"] = self.phase.value
        return data


@dataclass(frozen=True, slots=True)
class Scenario:
    scenario_id: str
    description: str
    order_id: str
    customer_id: str
    ticket_id: str
    original_minor_units: int
    currency: str
    contradiction_time: int
    actions: tuple[ScheduledAction, ...]
