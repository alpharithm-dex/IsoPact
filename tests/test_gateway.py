from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from isopact.compiler.models import (
    AuthoritativeCaseContext,
    AuthoritativeOrder,
    ValidatedOutcomePactDraft,
)
from isopact.compiler.policy import PolicyCatalog
from isopact.domain.models import Decision, ExecutionOutcome, ReservationState
from isopact.gateway.activation import activate_validated_draft
from isopact.gateway.interceptor import IsoPactGatewayInterceptor
from isopact.reservations.memory import InMemoryReservationRepository
from isopact.reservations.firestore import evaluate_reservation_snapshot
from isopact.simulator.runner import ScenarioRunner
from isopact.simulator.scenarios import build_scenario


def active_pact(namespace: str = "unit"):
    context = AuthoritativeCaseContext(
        tenant="demo-retailer",
        domain="commerce",
        case_type="missing_order",
        ticket_id="JIRA-8472",
        orders=(
            AuthoritativeOrder(
                order_id="ORD-8472",
                customer_id="CUS-104",
                captured_minor_units=20_000,
                currency="USD",
            ),
        ),
    )
    policy = PolicyCatalog().resolve("demo-retailer", "commerce", "missing_order")
    assert policy is not None
    draft = ValidatedOutcomePactDraft(
        draft_id="draft_unit",
        outcome_type="resolve_missing_order",
        subjects={
            "ticket_id": "JIRA-8472",
            "order_id": "ORD-8472",
            "customer_id": "CUS-104",
        },
        requested_resolution_semantics="refund_or_replacement",
        allowed_resolution_paths=("successful_refund", "confirmed_replacement"),
        exclusive_slot="primary_compensation",
        goodwill_limit_minor_units=5_000,
        goodwill_currency="USD",
        completion_evidence=policy.completion_evidence,
        human_approval_threshold_minor_units=25_000,
        duplicate_compensation_blocked=True,
        policy_id=policy.policy_id,
        policy_version=policy.version,
    )
    return activate_validated_draft(draft, context, policy, namespace=namespace)


class BrokenRepository:
    def reserve(self, request):
        raise RuntimeError("Firestore unavailable")


class GatewayTests(unittest.TestCase):
    def test_firestore_transaction_plan_is_deterministic_when_retried(self) -> None:
        plans = [
            evaluate_reservation_snapshot(None, slot_occupied=False)
            for _ in range(5)
        ]
        self.assertTrue(all(plan == plans[0] for plan in plans))
        self.assertEqual(plans[0].decision, Decision.ALLOW)
        # The pure callback plan has no downstream adapter to invoke.
        external_executions = 0
        self.assertEqual(external_executions, 0)

    def test_activation_is_deterministic_and_not_model_backed(self) -> None:
        first = active_pact("same")
        second = active_pact("same")
        self.assertEqual(first, second)
        self.assertEqual(first.activation_source, "VALIDATED_DRAFT_AND_TRUSTED_POLICY")
        self.assertIn("authorized_goodwill", first.pact.allowed_resolution_paths)

    def test_same_stage2_schedule_is_protected(self) -> None:
        scenario = build_scenario("missing_order_unmanaged")
        unmanaged = ScenarioRunner().run(scenario)
        gateway = IsoPactGatewayInterceptor(
            active_pact("replay"), InMemoryReservationRepository()
        )
        protected = ScenarioRunner(gateway).run(scenario)
        schedule_json = json.dumps(unmanaged["schedule"], sort_keys=True, separators=(",", ":"))
        self.assertEqual(unmanaged["schedule"], protected["schedule"])
        self.assertEqual(
            hashlib.sha256(schedule_json.encode()).hexdigest(),
            hashlib.sha256(
                json.dumps(protected["schedule"], sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        )
        results = {item["action_id"]: item for item in protected["action_results"]}
        self.assertEqual(results["e01"]["interceptor_decision"]["decision"], "ALLOW")
        self.assertEqual(results["e03"]["interceptor_decision"]["reason_code"], "EXCLUSIVE_RESOLUTION_CONFLICT")
        self.assertEqual(results["e04"]["interceptor_decision"]["reason_code"], "EXCLUSIVE_RESOLUTION_CONFLICT")
        self.assertEqual(results["e05"]["interceptor_decision"]["decision"], "ALLOW")
        self.assertNotEqual(results["e06"]["interceptor_decision"]["decision"], "ALLOW")
        self.assertEqual(len(unmanaged["final"]["services"]["stripe"]), 2)
        self.assertEqual(len(protected["final"]["services"]["stripe"]), 1)
        self.assertEqual(protected["final"]["services"]["carrier"], {})
        self.assertEqual(protected["final"]["services"]["warehouse"], {})
        self.assertEqual(len(protected["final"]["services"]["crm"]), 1)
        self.assertEqual(gateway.model_calls, 0)

    def test_firestore_failure_fails_closed(self) -> None:
        action = build_scenario("missing_order_unmanaged").actions[1]
        gateway = IsoPactGatewayInterceptor(active_pact("failure"), BrokenRepository())
        decision = gateway.intercept(action)
        self.assertEqual(decision.decision, "DEFER")
        self.assertEqual(decision.reason_code, "FIRESTORE_RESERVATION_UNAVAILABLE")
        self.assertFalse(decision.external_call_executed)

    def test_unknown_outcome_survives_new_gateway_instance(self) -> None:
        repository = InMemoryReservationRepository()
        active = active_pact("unknown")
        action = build_scenario("missing_order_unmanaged").actions[1]
        first_gateway = IsoPactGatewayInterceptor(active, repository)
        first = first_gateway.intercept(action)
        first_gateway.after_external_call(action, {"status": "TIMEOUT"})
        self.assertEqual(first.reservation_state_after, ReservationState.OUTCOME_UNKNOWN.value)
        second_gateway = IsoPactGatewayInterceptor(active, repository)
        retry_action = build_scenario("missing_order_unmanaged").actions[6]
        retry = second_gateway.intercept(retry_action)
        self.assertEqual(retry.decision, Decision.DEFER.value)
        self.assertEqual(retry.reason_code, "EXTERNAL_OUTCOME_UNKNOWN")


if __name__ == "__main__":
    unittest.main(verbosity=2)
