from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from isopact.simulator import ScenarioRunner, build_scenario
from isopact.simulator.clock import VirtualClock
from isopact.simulator.interception import InterceptionDecision
from isopact.simulator.ledger import EconomicLedger
from isopact.simulator.models import Scenario, ScheduledAction
from isopact.simulator.runner import canonical_json
from isopact.simulator.services import (
    CarrierService,
    CrmService,
    ExternalServiceTimeout,
    JiraService,
    StripeService,
    WarehouseService,
)


class BlockingTestInterceptor:
    def intercept(self, action: ScheduledAction) -> InterceptionDecision:
        if action.action_id == "e03":
            return InterceptionDecision("BLOCK", "TEST_POLICY_BLOCK")
        return InterceptionDecision("ALLOW", "TEST_ALLOW")


class EnterpriseSimulatorTests(unittest.TestCase):
    def test_unmanaged_contradiction_and_derived_economics(self) -> None:
        replay = ScenarioRunner().run(build_scenario("missing_order_unmanaged"))
        checkpoint = replay["checkpoints"]["contradiction"]
        services = checkpoint["services"]
        position = checkpoint["economic_position"]

        self.assertEqual(services["jira"]["JIRA-8472"]["status"], "CLOSED")
        self.assertEqual(services["stripe"]["REF-001"]["state"], "PENDING")
        self.assertEqual(services["stripe"]["REF-002"]["state"], "PENDING")
        self.assertEqual(services["carrier"]["SHIP-001"]["state"], "CREATED")
        self.assertEqual(services["warehouse"]["STK-001"]["state"], "RESERVED")
        self.assertEqual(services["crm"]["CR-001"]["state"], "ISSUED")
        self.assertEqual(services["crm"]["CR-001"]["amount_minor_units"], 5_000)

        self.assertEqual(position["original_minor_units"], 20_000)
        self.assertEqual(position["settled_minor_units"], 5_000)
        self.assertEqual(position["pending_minor_units"], 40_000)
        self.assertEqual(position["projected_only_minor_units"], 20_000)
        self.assertEqual(position["projected_total_minor_units"], 65_000)
        self.assertEqual(position["projected_excess_minor_units"], 45_000)
        self.assertEqual(position["authorized_exception_minor_units"], 5_000)
        self.assertEqual(sum(x["amount_minor_units"] for x in position["provenance"]), 65_000)

    def test_twenty_replays_have_one_semantic_digest(self) -> None:
        digests = {
            ScenarioRunner().run(build_scenario("missing_order_unmanaged"))["semantic_digest"]
            for _ in range(20)
        }
        self.assertEqual(len(digests), 1)
        print(f"METRIC replay_runs=20 unique_semantic_digests={len(digests)} digest={next(iter(digests))}")

    def test_transport_idempotency_is_not_business_idempotency(self) -> None:
        clock = VirtualClock()
        ledger = EconomicLedger()
        stripe = StripeService(clock, ledger)
        common = dict(
            order_id="ORD-8472", amount_minor_units=20_000, currency="USD",
            actor="support-a", session_id="session-a", settle_at=None,
        )
        first, _ = stripe.create_refund(idempotency_key="same-key", **common)
        retry, _ = stripe.create_refund(idempotency_key="same-key", **common)
        self.assertEqual(first["refund_id"], retry["refund_id"])
        self.assertEqual(len(stripe.refunds), 1)

        stripe.create_refund(
            idempotency_key="different-key", **{**common, "actor": "support-b", "session_id": "session-b"}
        )
        self.assertEqual(len(stripe.refunds), 2)
        self.assertNotEqual(stripe.refunds["REF-001"]["actor"], stripe.refunds["REF-002"]["actor"])
        print("METRIC same_transport_key_external_objects=1 different_keys_same_business_outcome_objects=2")

    def test_interceptor_is_interchangeable_and_blocks_before_external_call(self) -> None:
        replay = ScenarioRunner(BlockingTestInterceptor()).run(
            build_scenario("missing_order_unmanaged")
        )
        result = next(x for x in replay["action_results"] if x["action_id"] == "e03")
        self.assertFalse(result["external_call_executed"])
        self.assertEqual(result["interceptor_decision"]["decision"], "BLOCK")
        self.assertEqual(replay["final"]["services"]["carrier"], {})

    def test_preexisting_divergence_is_outside_boundary_and_reversible(self) -> None:
        replay = ScenarioRunner().run(build_scenario("missing_order_preexisting_divergence"))
        schedule = {action["action_id"]: action for action in replay["schedule"]}
        services = replay["checkpoints"]["contradiction"]["services"]
        self.assertFalse(schedule["p01"]["enforcement_boundary"])
        self.assertFalse(schedule["p02"]["enforcement_boundary"])
        self.assertEqual(services["carrier"]["SHIP-001"]["state"], "CREATED")
        self.assertEqual(services["warehouse"]["STK-001"]["state"], "RESERVED")

    def test_delayed_success_occurs_after_ticket_closure(self) -> None:
        replay = ScenarioRunner().run(build_scenario("missing_order_unmanaged"))
        close = next(x for x in replay["action_results"] if x["action_id"] == "e02")
        settled = next(
            x for x in replay["economic_events"]
            if x["event_type"] == "REFUND_SETTLED" and x["external_object_id"] == "REF-001"
        )
        self.assertEqual(close["logical_time"], 200)
        self.assertEqual(settled["logical_timestamp"], 1000)
        self.assertEqual(replay["final"]["services"]["stripe"]["REF-001"]["state"], "SUCCEEDED")

    def test_delayed_failed_refund(self) -> None:
        clock = VirtualClock()
        ledger = EconomicLedger()
        stripe = StripeService(clock, ledger)
        refund, _ = stripe.create_refund(
            order_id="ORD-8472", amount_minor_units=20_000, currency="USD",
            idempotency_key="failure-key", actor="support", session_id="session",
            settle_at=120, settlement_outcome="FAILED",
        )
        self.assertEqual(refund["state"], "PENDING")
        clock.advance_to(120)
        self.assertEqual(refund["state"], "FAILED")
        self.assertEqual(ledger.events[-1].event_type, "REFUND_FAILED")

    def test_carrier_label_becomes_irreversible(self) -> None:
        clock = VirtualClock()
        ledger = EconomicLedger()
        carrier = CarrierService(clock, ledger)
        shipment = carrier.create_label(
            order_id="ORD-8472", value_minor_units=20_000, currency="USD", actor="fulfillment"
        )
        carrier.accept(shipment["shipment_id"])
        with self.assertRaisesRegex(ValueError, "reversible only while CREATED"):
            carrier.cancel(shipment["shipment_id"])
        carrier.dispatch(shipment["shipment_id"])
        self.assertEqual(shipment["state"], "DISPATCHED")

    def test_external_timeout_is_representable(self) -> None:
        scenario = Scenario(
            "timeout", "timeout fixture", "ORD-8472", "CUS-104", "JIRA-8472",
            20_000, "USD", 100,
            (
                ScheduledAction("t00", 0, "customer", "jira", "create_ticket", {}),
                ScheduledAction(
                    "t01", 10, "support", "stripe", "create_refund",
                    {"amount_minor_units": 20_000, "currency": "USD", "idempotency_key": "timeout", "session_id": "s", "settle_at": None, "timeout": True},
                ),
            ),
        )
        replay = ScenarioRunner().run(scenario)
        result = next(x for x in replay["action_results"] if x["action_id"] == "t01")
        self.assertEqual(result["immediate_result"]["status"], "TIMEOUT")
        self.assertEqual(replay["final"]["services"]["stripe"], {})

    def test_services_do_not_hold_cross_system_references(self) -> None:
        clock = VirtualClock()
        ledger = EconomicLedger()
        services = [
            JiraService(), StripeService(clock, ledger), CarrierService(clock, ledger),
            WarehouseService(), CrmService(clock, ledger),
        ]
        forbidden = {"jira", "stripe", "carrier", "warehouse", "crm"}
        for service in services:
            names = set(vars(service)) & forbidden
            self.assertEqual(names, set())


if __name__ == "__main__":
    unittest.main(verbosity=2)
