from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class Decision(StrEnum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    DEFER = "DEFER"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class ReservationState(StrEnum):
    RESERVED = "RESERVED"
    EXECUTING = "EXECUTING"
    CONFIRMED = "CONFIRMED"
    FAILED_AUTHORITATIVELY = "FAILED_AUTHORITATIVELY"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"
    REVERSED = "REVERSED"
    EXPIRED = "EXPIRED"


class ExecutionOutcome(StrEnum):
    CONFIRMED = "CONFIRMED"
    FAILED_AUTHORITATIVELY = "FAILED_AUTHORITATIVELY"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"


class ReasonCode(StrEnum):
    AUTHORITY_RESERVED = "AUTHORITY_RESERVED"
    DUPLICATE_OPERATION = "DUPLICATE_OPERATION"
    EXCLUSIVE_RESOLUTION_CONFLICT = "EXCLUSIVE_RESOLUTION_CONFLICT"
    OPERATION_IN_PROGRESS = "OPERATION_IN_PROGRESS"
    EXTERNAL_OUTCOME_UNKNOWN = "EXTERNAL_OUTCOME_UNKNOWN"
    AUTHORITATIVE_FAILURE_RETRY = "AUTHORITATIVE_FAILURE_RETRY"
    POLICY_APPROVAL_REQUIRED = "POLICY_APPROVAL_REQUIRED"


@dataclass(frozen=True, slots=True)
class PolicyVersion:
    policy_id: str
    version: str

    @property
    def reference(self) -> str:
        return f"{self.policy_id}@{self.version}"


@dataclass(frozen=True, slots=True)
class Money:
    currency: str
    minor_units: int

    def __post_init__(self) -> None:
        currency = self.currency.strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("currency must be a three-letter ISO-style code")
        if isinstance(self.minor_units, bool) or not isinstance(self.minor_units, int):
            raise TypeError("minor_units must be an integer")
        if self.minor_units < 0:
            raise ValueError("minor_units must be non-negative")
        object.__setattr__(self, "currency", currency)

    @classmethod
    def from_major(cls, amount: str | int | Decimal, currency: str) -> Money:
        try:
            decimal = Decimal(str(amount))
        except InvalidOperation as exc:
            raise ValueError("invalid monetary amount") from exc
        quantized = decimal.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        if decimal != quantized:
            raise ValueError("amount has excess precision for minor units")
        minor = quantized * 100
        if minor != minor.to_integral_value():
            raise ValueError("amount cannot be represented in minor units")
        return cls(currency=currency, minor_units=int(minor))


@dataclass(frozen=True, slots=True)
class ResolutionSlot:
    name: str


@dataclass(frozen=True, slots=True)
class OutcomePact:
    pact_id: str
    transaction: Money
    allowed_resolution_paths: frozenset[str]
    exclusive_slots: Mapping[str, frozenset[str]]
    policy: PolicyVersion

    def __post_init__(self) -> None:
        if not self.pact_id.strip():
            raise ValueError("pact_id is required")
        frozen = {name: frozenset(paths) for name, paths in self.exclusive_slots.items()}
        object.__setattr__(self, "exclusive_slots", MappingProxyType(frozen))

    def slot_for(self, resolution_path: str) -> ResolutionSlot | None:
        for name, paths in self.exclusive_slots.items():
            if resolution_path in paths:
                return ResolutionSlot(name)
        return None


@dataclass(frozen=True, slots=True)
class OperationIntent:
    pact_id: str
    resolution_path: str
    event_type: str
    subject_id: str
    amount: Money | None
    resource: str | None
    policy: PolicyVersion
    agent_id: str
    request_id: str
    session_id: str
    trace_id: str


@dataclass(frozen=True, slots=True)
class CanonicalOperation:
    pact_id: str
    resolution_path: str
    event_type: str
    subject_id: str
    normalized_value: str
    operation_key: str
    policy: PolicyVersion


@dataclass(frozen=True, slots=True)
class OperationReservation:
    pact_id: str
    operation_key: str
    canonical_operation: CanonicalOperation
    slot: ResolutionSlot | None
    state: ReservationState
    authorization_policy: PolicyVersion
    first_agent_id: str
    attempt_count: int = 1
    state_history: tuple[ReservationState, ...] = field(
        default_factory=lambda: (ReservationState.RESERVED,)
    )

    def transition(self, state: ReservationState) -> OperationReservation:
        return replace(self, state=state, state_history=(*self.state_history, state))

    def retry_under(self, policy: PolicyVersion, agent_id: str) -> OperationReservation:
        return replace(
            self,
            state=ReservationState.RESERVED,
            authorization_policy=policy,
            first_agent_id=agent_id,
            attempt_count=self.attempt_count + 1,
            state_history=(*self.state_history, ReservationState.RESERVED),
        )


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    pact_id: str
    operation_key: str
    requested_resolution_slot: str | None
    reservation_state: ReservationState
    decision: Decision
    reason_code: ReasonCode
    policy_reference: str
    existing_conflicting_reservation: str | None = None
