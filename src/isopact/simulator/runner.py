from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict
from typing import Any

from .clock import VirtualClock
from .interception import AllowAllInterceptor, InterceptionPort
from .ledger import EconomicLedger
from .models import ActionResult, Scenario, ScheduledAction
from .services import (
    CarrierService,
    CrmService,
    ExternalServiceTimeout,
    JiraService,
    StripeService,
    WarehouseService,
)


def canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def semantic_digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class ScenarioRunner:
    def __init__(self, interceptor: InterceptionPort | None = None) -> None:
        self.interceptor = interceptor or AllowAllInterceptor()

    def run(self, scenario: Scenario) -> dict[str, Any]:
        self.clock = VirtualClock()
        self.ledger = EconomicLedger()
        self.jira = JiraService()
        self.stripe = StripeService(self.clock, self.ledger)
        self.carrier = CarrierService(self.clock, self.ledger)
        self.warehouse = WarehouseService()
        self.crm = CrmService(self.clock, self.ledger)
        self.results: list[ActionResult] = []
        self.checkpoints: dict[str, Any] = {}

        for action in scenario.actions:
            self.clock.schedule_at(
                action.logical_time,
                f"action.{action.action_id}",
                lambda current=action: self._execute(current, scenario),
                {"action_id": action.action_id, "target_system": action.target_system},
            )
        self.clock.advance_to(scenario.contradiction_time)
        self.checkpoints["contradiction"] = self._snapshot(scenario, scenario.contradiction_time)
        queued_at_contradiction = self.clock.inspect_queue()
        self.clock.run_until_idle()
        final = self._snapshot(scenario, self.clock.now)
        replay = {
            "schema_version": "stage2-replay-v1",
            "scenario": {
                "scenario_id": scenario.scenario_id,
                "description": scenario.description,
                "order_id": scenario.order_id,
                "customer_id": scenario.customer_id,
                "ticket_id": scenario.ticket_id,
                "original_minor_units": scenario.original_minor_units,
                "currency": scenario.currency,
                "contradiction_time": scenario.contradiction_time,
            },
            "schedule": [action.to_dict() for action in scenario.actions],
            "action_results": [result.to_dict() for result in self.results],
            "queued_at_contradiction": queued_at_contradiction,
            "economic_events": [event.to_dict() for event in self.ledger.events],
            "checkpoints": self.checkpoints,
            "final": final,
        }
        replay["semantic_digest"] = semantic_digest(replay)
        return replay

    def _execute(self, action: ScheduledAction, scenario: Scenario) -> None:
        decision = self.interceptor.intercept(action)
        if decision.decision != "ALLOW":
            self.results.append(
                ActionResult(
                    action.action_id, self.clock.now, action.actor, action.target_system,
                    action.tool, copy.deepcopy(action.inputs), asdict(decision), False, None,
                    {"status": "NOT_EXECUTED"}, [],
                )
            )
            return
        external_id: str | None = None
        followups: list[dict[str, Any]] = []
        try:
            immediate = self._dispatch(action, scenario)
            if isinstance(immediate, tuple):
                payload, followups = immediate
            else:
                payload = immediate
            external_id = next(
                (payload[key] for key in ("refund_id", "shipment_id", "reservation_id", "credit_id", "ticket_id") if key in payload),
                None,
            )
            result = {"status": "OK", "object": copy.deepcopy(payload)}
        except ExternalServiceTimeout as exc:
            result = {"status": "TIMEOUT", "error": str(exc)}
        after_call = getattr(self.interceptor, "after_external_call", None)
        if after_call is not None:
            after_call(action, result)
        self.results.append(
            ActionResult(
                action.action_id, self.clock.now, action.actor, action.target_system,
                action.tool, copy.deepcopy(action.inputs), asdict(decision), True, external_id,
                result, followups,
            )
        )

    def _dispatch(self, action: ScheduledAction, scenario: Scenario) -> Any:
        values = action.inputs
        if action.target_system == "jira" and action.tool == "create_ticket":
            return self.jira.create_ticket(scenario.ticket_id, scenario.order_id, scenario.customer_id)
        if action.target_system == "jira" and action.tool == "close_ticket":
            return self.jira.close_ticket(scenario.ticket_id, action.actor, str(values["reason"]), self.clock.now)
        if action.target_system == "stripe" and action.tool == "create_refund":
            return self.stripe.create_refund(
                order_id=scenario.order_id,
                amount_minor_units=int(values["amount_minor_units"]),
                currency=str(values["currency"]),
                idempotency_key=str(values["idempotency_key"]),
                actor=action.actor,
                session_id=str(values["session_id"]),
                settle_at=int(values["settle_at"]) if values.get("settle_at") is not None else None,
                settlement_outcome=str(values.get("settlement_outcome", "SUCCEEDED")),
                timeout=bool(values.get("timeout", False)),
            )
        if action.target_system == "carrier" and action.tool == "create_label":
            return self.carrier.create_label(
                order_id=scenario.order_id,
                value_minor_units=int(values["value_minor_units"]),
                currency=str(values["currency"]),
                actor=action.actor,
            )
        if action.target_system == "warehouse" and action.tool == "reserve_stock":
            return self.warehouse.reserve(
                scenario.order_id, str(values["resource"]), int(values["quantity"]), action.actor
            )
        if action.target_system == "crm" and action.tool == "issue_credit":
            return self.crm.issue_credit(
                scenario.customer_id, scenario.order_id, int(values["amount_minor_units"]),
                str(values["currency"]), action.actor,
            )
        raise ValueError(f"unsupported action {action.target_system}.{action.tool}")

    def _snapshot(self, scenario: Scenario, as_of: int) -> dict[str, Any]:
        return {
            "logical_time": as_of,
            "services": {
                "jira": copy.deepcopy(self.jira.tickets),
                "stripe": copy.deepcopy(self.stripe.refunds),
                "carrier": copy.deepcopy(self.carrier.shipments),
                "warehouse": copy.deepcopy(self.warehouse.reservations),
                "crm": copy.deepcopy(self.crm.credits),
            },
            "economic_position": self.ledger.position(
                as_of=as_of,
                original_minor_units=scenario.original_minor_units,
                currency=scenario.currency,
            ).to_dict(),
        }
