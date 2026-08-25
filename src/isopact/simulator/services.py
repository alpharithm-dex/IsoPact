from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from .clock import VirtualClock
from .ledger import EconomicLedger
from .models import EconomicPhase


class ExternalServiceTimeout(RuntimeError):
    pass


class RefundState(StrEnum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ShipmentState(StrEnum):
    CREATED = "CREATED"
    ACCEPTED = "ACCEPTED"
    DISPATCHED = "DISPATCHED"
    CANCELLED = "CANCELLED"


class StockState(StrEnum):
    RESERVED = "RESERVED"
    RELEASED = "RELEASED"
    DISPATCHED = "DISPATCHED"


class CreditState(StrEnum):
    ISSUED = "ISSUED"
    USED = "USED"
    REVERSED = "REVERSED"


class JiraService:
    def __init__(self) -> None:
        self.tickets: dict[str, dict[str, Any]] = {}

    def create_ticket(self, ticket_id: str, order_id: str, customer_id: str) -> dict[str, Any]:
        ticket = {
            "ticket_id": ticket_id,
            "order_id": order_id,
            "customer_id": customer_id,
            "status": "OPEN",
            "closed_at": None,
            "closed_by": None,
            "close_reason": None,
            "comments": [],
            "settlement_metadata": None,
        }
        self.tickets[ticket_id] = ticket
        return ticket

    def close_ticket(self, ticket_id: str, actor: str, reason: str, now: int) -> dict[str, Any]:
        ticket = self.tickets[ticket_id]
        ticket.update(status="CLOSED", closed_at=now, closed_by=actor, close_reason=reason)
        return ticket

    def reopen_ticket(self, ticket_id: str, actor: str, reason: str) -> dict[str, Any]:
        ticket = self.tickets[ticket_id]
        ticket.update(status="OPEN", closed_at=None, closed_by=None, close_reason=None)
        ticket["comments"].append({"actor": actor, "text": reason})
        return ticket

    def add_comment(self, ticket_id: str, actor: str, text: str) -> None:
        self.tickets[ticket_id]["comments"].append({"actor": actor, "text": text})

    def attach_settlement_metadata(self, ticket_id: str, metadata: dict[str, Any]) -> None:
        self.tickets[ticket_id]["settlement_metadata"] = dict(metadata)

    def get_ticket(self, ticket_id: str) -> dict[str, Any]:
        return self.tickets[ticket_id]


class StripeService:
    def __init__(self, clock: VirtualClock, ledger: EconomicLedger) -> None:
        self.clock = clock
        self.ledger = ledger
        self.refunds: dict[str, dict[str, Any]] = {}
        self._idempotency: dict[str, str] = {}
        self._counter = 0
        self.create_call_count = 0

    def create_refund(
        self,
        *,
        order_id: str,
        amount_minor_units: int,
        currency: str,
        idempotency_key: str,
        actor: str,
        session_id: str,
        settle_at: int | None,
        settlement_outcome: str = "SUCCEEDED",
        timeout: bool = False,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        self.create_call_count += 1
        if timeout:
            raise ExternalServiceTimeout("deterministic Stripe timeout")
        if idempotency_key in self._idempotency:
            refund_id = self._idempotency[idempotency_key]
            return self.refunds[refund_id], []
        self._counter += 1
        refund_id = f"REF-{self._counter:03d}"
        refund = {
            "refund_id": refund_id,
            "order_id": order_id,
            "amount_minor_units": amount_minor_units,
            "currency": currency,
            "state": RefundState.PENDING.value,
            "idempotency_key": idempotency_key,
            "actor": actor,
            "session_id": session_id,
        }
        self.refunds[refund_id] = refund
        self._idempotency[idempotency_key] = refund_id
        self.ledger.append(
            logical_timestamp=self.clock.now,
            source_system="stripe",
            event_type="REFUND_PENDING",
            phase=EconomicPhase.PENDING,
            subject_id=order_id,
            external_object_id=refund_id,
            amount_minor_units=amount_minor_units,
            currency=currency,
            actor=actor,
            session_id=session_id,
        )
        followups: list[dict[str, Any]] = []
        if settle_at is not None:
            event_id = f"stripe.settlement.{refund_id}"

            def settle() -> None:
                target = RefundState(settlement_outcome)
                refund["state"] = target.value
                self.ledger.append(
                    logical_timestamp=self.clock.now,
                    source_system="stripe",
                    event_type=("REFUND_SETTLED" if target is RefundState.SUCCEEDED else "REFUND_FAILED"),
                    phase=(EconomicPhase.SETTLED if target is RefundState.SUCCEEDED else EconomicPhase.FAILED),
                    subject_id=order_id,
                    external_object_id=refund_id,
                    amount_minor_units=amount_minor_units,
                    currency=currency,
                    actor="stripe-system",
                    session_id=None,
                )

            metadata = {"refund_id": refund_id, "outcome": settlement_outcome}
            self.clock.schedule_at(settle_at, event_id, settle, metadata)
            followups.append({"event_id": event_id, "logical_time": settle_at, **metadata})
        return refund, followups

    def get_refund(self, refund_id: str) -> dict[str, Any]:
        return self.refunds[refund_id]


class CarrierService:
    def __init__(self, clock: VirtualClock, ledger: EconomicLedger) -> None:
        self.clock = clock
        self.ledger = ledger
        self.shipments: dict[str, dict[str, Any]] = {}
        self._counter = 0

    def create_label(
        self, *, order_id: str, value_minor_units: int, currency: str, actor: str
    ) -> dict[str, Any]:
        self._counter += 1
        shipment_id = f"SHIP-{self._counter:03d}"
        shipment = {
            "shipment_id": shipment_id,
            "order_id": order_id,
            "value_minor_units": value_minor_units,
            "currency": currency,
            "state": ShipmentState.CREATED.value,
            "actor": actor,
        }
        self.shipments[shipment_id] = shipment
        self.ledger.append(
            logical_timestamp=self.clock.now,
            source_system="carrier",
            event_type="REPLACEMENT_CREATED",
            phase=EconomicPhase.PROJECTED,
            subject_id=order_id,
            external_object_id=shipment_id,
            amount_minor_units=value_minor_units,
            currency=currency,
            actor=actor,
            session_id=None,
        )
        return shipment

    def accept(self, shipment_id: str) -> dict[str, Any]:
        shipment = self.shipments[shipment_id]
        if shipment["state"] != ShipmentState.CREATED:
            raise ValueError("only a created label can be accepted")
        shipment["state"] = ShipmentState.ACCEPTED.value
        return shipment

    def dispatch(self, shipment_id: str) -> dict[str, Any]:
        shipment = self.shipments[shipment_id]
        if shipment["state"] not in {ShipmentState.CREATED, ShipmentState.ACCEPTED}:
            raise ValueError("shipment cannot be dispatched")
        shipment["state"] = ShipmentState.DISPATCHED.value
        self.ledger.append(
            logical_timestamp=self.clock.now,
            source_system="carrier",
            event_type="REPLACEMENT_DISPATCHED",
            phase=EconomicPhase.SETTLED,
            subject_id=shipment["order_id"],
            external_object_id=shipment_id,
            amount_minor_units=shipment["value_minor_units"],
            currency=shipment["currency"],
            actor="carrier-system",
            session_id=None,
        )
        return shipment

    def cancel(self, shipment_id: str) -> dict[str, Any]:
        shipment = self.shipments[shipment_id]
        if shipment["state"] != ShipmentState.CREATED:
            raise ValueError("label is reversible only while CREATED")
        shipment["state"] = ShipmentState.CANCELLED.value
        self.ledger.append(
            logical_timestamp=self.clock.now,
            source_system="carrier",
            event_type="REPLACEMENT_CANCELLED",
            phase=EconomicPhase.REVERSED,
            subject_id=shipment["order_id"],
            external_object_id=shipment_id,
            amount_minor_units=shipment["value_minor_units"],
            currency=shipment["currency"],
            actor="carrier-system",
            session_id=None,
        )
        return shipment

    def get_shipment(self, shipment_id: str) -> dict[str, Any]:
        return self.shipments[shipment_id]


class WarehouseService:
    def __init__(self) -> None:
        self.reservations: dict[str, dict[str, Any]] = {}
        self._counter = 0

    def reserve(self, order_id: str, resource: str, quantity: int, actor: str) -> dict[str, Any]:
        self._counter += 1
        reservation_id = f"STK-{self._counter:03d}"
        item = {
            "reservation_id": reservation_id,
            "order_id": order_id,
            "resource": resource,
            "quantity": quantity,
            "state": StockState.RESERVED.value,
            "actor": actor,
        }
        self.reservations[reservation_id] = item
        return item

    def release(self, reservation_id: str) -> dict[str, Any]:
        item = self.reservations[reservation_id]
        if item["state"] != StockState.RESERVED:
            raise ValueError("only reserved stock can be released")
        item["state"] = StockState.RELEASED.value
        return item

    def dispatch(self, reservation_id: str) -> dict[str, Any]:
        item = self.reservations[reservation_id]
        if item["state"] != StockState.RESERVED:
            raise ValueError("only reserved stock can dispatch")
        item["state"] = StockState.DISPATCHED.value
        return item

    def get_reservation(self, reservation_id: str) -> dict[str, Any]:
        return self.reservations[reservation_id]


class CrmService:
    def __init__(self, clock: VirtualClock, ledger: EconomicLedger) -> None:
        self.clock = clock
        self.ledger = ledger
        self.credits: dict[str, dict[str, Any]] = {}
        self._counter = 0

    def issue_credit(
        self, customer_id: str, order_id: str, amount_minor_units: int, currency: str, actor: str
    ) -> dict[str, Any]:
        self._counter += 1
        credit_id = f"CR-{self._counter:03d}"
        credit = {
            "credit_id": credit_id,
            "customer_id": customer_id,
            "order_id": order_id,
            "amount_minor_units": amount_minor_units,
            "currency": currency,
            "state": CreditState.ISSUED.value,
            "actor": actor,
            "source_action": "authorized_missing_order_goodwill",
        }
        self.credits[credit_id] = credit
        self.ledger.append(
            logical_timestamp=self.clock.now,
            source_system="crm",
            event_type="GOODWILL_CREDIT_ISSUED",
            phase=EconomicPhase.SETTLED,
            subject_id=order_id,
            external_object_id=credit_id,
            amount_minor_units=amount_minor_units,
            currency=currency,
            actor=actor,
            session_id=None,
            authorized_exception=True,
        )
        return credit

    def reverse(self, credit_id: str) -> dict[str, Any]:
        credit = self.credits[credit_id]
        if credit["state"] != CreditState.ISSUED:
            raise ValueError("only unused issued credit is reversible")
        credit["state"] = CreditState.REVERSED.value
        self.ledger.append(
            logical_timestamp=self.clock.now,
            source_system="crm",
            event_type="GOODWILL_CREDIT_REVERSED",
            phase=EconomicPhase.REVERSED,
            subject_id=credit["order_id"],
            external_object_id=credit_id,
            amount_minor_units=credit["amount_minor_units"],
            currency=credit["currency"],
            actor="crm-system",
            session_id=None,
            authorized_exception=True,
        )
        return credit

    def get_credit(self, credit_id: str) -> dict[str, Any]:
        return self.credits[credit_id]


def service_snapshot(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return value
