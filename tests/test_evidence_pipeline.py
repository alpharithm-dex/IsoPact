from __future__ import annotations

import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from isopact.compiler.models import (
    AuthoritativeCaseContext,
    AuthoritativeOrder,
    ValidatedOutcomePactDraft,
)
from isopact.compiler.policy import PolicyCatalog
from isopact.domain.models import ReservationState
from isopact.evidence.memory import InMemoryPactGraphRepository
from isopact.evidence.models import (
    ClaimType,
    EvidenceDelivery,
    EvidenceRank,
    ImmediateState,
    PactLifecycle,
    StateClaim,
)
from isopact.evidence.pipeline import EvidencePipeline
from isopact.evidence.query import StripeQueryEvidenceProvider
from isopact.gateway.activation import activate_validated_draft
from isopact.gateway.interceptor import IsoPactGatewayInterceptor
from isopact.reservations.memory import InMemoryReservationRepository
from isopact.simulator.models import ScheduledAction


def active_pact(namespace: str = "evidence"):
    context = AuthoritativeCaseContext(
        tenant="demo-retailer", domain="commerce", case_type="missing_order",
        ticket_id="JIRA-8472",
        orders=(AuthoritativeOrder(order_id="ORD-8472", customer_id="CUS-104", captured_minor_units=20_000, currency="USD"),),
    )
    policy = PolicyCatalog().resolve("demo-retailer", "commerce", "missing_order")
    assert policy is not None
    draft = ValidatedOutcomePactDraft(
        draft_id="draft_evidence", outcome_type="resolve_missing_order",
        subjects={"ticket_id": "JIRA-8472", "order_id": "ORD-8472", "customer_id": "CUS-104"},
        requested_resolution_semantics="refund_or_replacement",
        allowed_resolution_paths=("successful_refund", "confirmed_replacement"),
        exclusive_slot="primary_compensation", goodwill_limit_minor_units=5_000,
        goodwill_currency="USD", completion_evidence=policy.completion_evidence,
        human_approval_threshold_minor_units=25_000, duplicate_compensation_blocked=True,
        policy_id=policy.policy_id, policy_version=policy.version,
    )
    return activate_validated_draft(draft, context, policy, namespace=namespace)


def pending_claim(pact_id: str, operation: str = "op-refund") -> StateClaim:
    return StateClaim(
        claim_id="claim-pending", pact_id=pact_id, claim_type=ClaimType.API_RESPONSE,
        source_system="stripe", source_actor="support-a", subject="ORD-8472",
        external_object_id="REF-001", operation_identity=operation,
        resolution_path="successful_refund", immediate_state=ImmediateState.PENDING,
        evidence_rank=EvidenceRank.ACCEPTED_PENDING_RESPONSE,
        occurred_at="2026-08-23T20:00:01+00:00", ingested_at="2026-08-23T20:00:02+00:00",
        trace_id="trace-pending",
    )


def event(
    pact_id: str,
    source_event_id: str = "evt-success",
    event_type: str = "stripe.refund.succeeded",
    operation: str = "op-refund",
    occurred_at: str = "2026-08-23T20:10:00+00:00",
    attempt: int = 1,
) -> dict[str, object]:
    return {
        "pact_id": pact_id, "source_system": "stripe", "source_event_id": source_event_id,
        "event_type": event_type, "subject": "ORD-8472", "external_object_id": "REF-001",
        "operation_identity": operation, "operation_attempt": attempt,
        "occurred_at": occurred_at, "ingested_at": "2026-08-23T20:11:00+00:00",
        "trace_id": f"trace-{source_event_id}",
    }


def delivery(message_id: str) -> EvidenceDelivery:
    return EvidenceDelivery(
        delivery_id=f"pubsub_{message_id}", delivery_mechanism="GOOGLE_CLOUD_PUBSUB",
        pubsub_message_id=message_id, publish_timestamp="2026-08-23T20:10:01+00:00",
        received_at="2026-08-23T20:11:00+00:00",
    )


class EvidencePipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.active = active_pact(self.id().split(".")[-1])
        self.repository = InMemoryPactGraphRepository()
        self.repository.activate_graph(self.active, "2026-08-23T20:00:00+00:00")
        self.pipeline = EvidencePipeline(self.repository)

    def test_pending_closed_and_agent_complete_cannot_settle(self) -> None:
        self.pipeline.record_claim(pending_claim(self.active.pact.pact_id))
        for claim_id, state, rank in (
            ("claim-jira", ImmediateState.CLOSED, EvidenceRank.ACCEPTED_PENDING_RESPONSE),
            ("claim-agent", ImmediateState.COMPLETE, EvidenceRank.AGENT_INTERPRETATION),
        ):
            self.pipeline.record_claim(StateClaim(
                claim_id=claim_id, pact_id=self.active.pact.pact_id,
                claim_type=ClaimType.SYSTEM_STATE if claim_id == "claim-jira" else ClaimType.AGENT_ASSERTION,
                source_system="jira" if claim_id == "claim-jira" else "agent",
                source_actor="support-a", subject="ORD-8472", external_object_id="JIRA-8472",
                operation_identity=None, resolution_path=None, immediate_state=state,
                evidence_rank=rank, occurred_at="2026-08-23T20:01:00+00:00",
                ingested_at="2026-08-23T20:01:01+00:00", trace_id=claim_id,
            ))
        snapshot = self.repository.snapshot(self.active.pact.pact_id)
        self.assertEqual(snapshot.state, PactLifecycle.PENDING)
        self.assertEqual(snapshot.evidence_count, 0)
        self.assertEqual(snapshot.claim_count, 3)

    def test_additive_goodwill_does_not_replace_selected_primary_resolution(self) -> None:
        self.pipeline.record_claim(pending_claim(self.active.pact.pact_id))
        self.pipeline.record_claim(StateClaim(
            claim_id="claim-goodwill", pact_id=self.active.pact.pact_id,
            claim_type=ClaimType.API_RESPONSE, source_system="crm",
            source_actor="retention-a", subject="CUS-104", external_object_id="CR-001",
            operation_identity="op-goodwill", resolution_path="authorized_goodwill",
            immediate_state=ImmediateState.ACCEPTED,
            evidence_rank=EvidenceRank.ACCEPTED_PENDING_RESPONSE,
            occurred_at="2026-08-23T20:02:00+00:00",
            ingested_at="2026-08-23T20:02:01+00:00", trace_id="trace-goodwill",
        ))
        before = self.repository.snapshot(self.active.pact.pact_id)
        self.assertEqual(before.selected_resolution, "successful_refund")
        self.assertEqual(before.state, PactLifecycle.PENDING)
        self.pipeline.ingest_event(event(self.active.pact.pact_id), delivery("goodwill-plus-refund"))
        self.assertEqual(self.repository.snapshot(self.active.pact.pact_id).state, PactLifecycle.SETTLED)

    def test_authoritative_success_settles_once(self) -> None:
        self.pipeline.record_claim(pending_claim(self.active.pact.pact_id))
        first = self.pipeline.ingest_event(event(self.active.pact.pact_id), delivery("m1"))
        second = self.pipeline.ingest_event(event(self.active.pact.pact_id), delivery("m2"))
        snapshot = self.repository.snapshot(self.active.pact.pact_id)
        self.assertTrue(first.settlement_transition_created)
        self.assertFalse(second.logical_evidence_created)
        self.assertEqual(snapshot.state, PactLifecycle.SETTLED)
        self.assertEqual(snapshot.settlement_transition_count, 1)
        self.assertEqual(snapshot.evidence_count, 1)
        self.assertEqual(snapshot.delivery_count, 2)
        self.assertEqual(snapshot.economic_event_count, 1)
        self.assertEqual(snapshot.settlement_proof_count, 1)

    def test_distinct_transport_ids_same_source_event_deduplicate(self) -> None:
        self.pipeline.record_claim(pending_claim(self.active.pact.pact_id))
        results = [
            self.pipeline.ingest_event(event(self.active.pact.pact_id), delivery(message_id))
            for message_id in ("transport-A", "transport-B")
        ]
        self.assertEqual(sum(result.logical_evidence_created for result in results), 1)
        snapshot = self.repository.snapshot(self.active.pact.pact_id)
        self.assertEqual(snapshot.evidence_count, 1)
        self.assertEqual(snapshot.delivery_count, 2)

    def test_concurrent_duplicate_ingestion_is_idempotent(self) -> None:
        self.pipeline.record_claim(pending_claim(self.active.pact.pact_id))
        barrier = threading.Barrier(25)
        def ingest(index: int):
            barrier.wait()
            return self.pipeline.ingest_event(event(self.active.pact.pact_id), delivery(f"worker-{index}"))
        with ThreadPoolExecutor(max_workers=25) as pool:
            results = list(pool.map(ingest, range(25)))
        snapshot = self.repository.snapshot(self.active.pact.pact_id)
        self.assertEqual(sum(result.logical_evidence_created for result in results), 1)
        self.assertEqual(snapshot.evidence_count, 1)
        self.assertEqual(snapshot.delivery_count, 25)
        self.assertEqual(snapshot.settlement_transition_count, 1)
        self.assertEqual(snapshot.economic_event_count, 1)

    def test_out_of_order_pending_does_not_regress_success(self) -> None:
        self.pipeline.ingest_event(event(self.active.pact.pact_id), delivery("success-first"))
        self.pipeline.ingest_event(
            event(
                self.active.pact.pact_id, source_event_id="evt-old-pending",
                event_type="stripe.refund.pending", occurred_at="2026-08-23T19:59:00+00:00",
            ),
            delivery("pending-later"),
        )
        snapshot = self.repository.snapshot(self.active.pact.pact_id)
        resolved = snapshot.resolved_operations["op-refund"]
        self.assertEqual(resolved["state"], "SUCCEEDED")
        self.assertEqual(resolved["rank"], 1)
        self.assertEqual(snapshot.state, PactLifecycle.SETTLED)

    def test_older_attempt_failure_does_not_override_newer_success(self) -> None:
        self.pipeline.ingest_event(event(self.active.pact.pact_id, attempt=2), delivery("new-success"))
        self.pipeline.ingest_event(
            event(
                self.active.pact.pact_id, source_event_id="evt-old-failure",
                event_type="stripe.refund.failed", occurred_at="2026-08-23T20:20:00+00:00", attempt=1,
            ), delivery("old-failure"),
        )
        resolved = self.repository.snapshot(self.active.pact.pact_id).resolved_operations["op-refund"]
        self.assertEqual(resolved["state"], "SUCCEEDED")
        self.assertEqual(resolved["attempt"], 2)

    def test_authoritative_failure_does_not_settle(self) -> None:
        self.pipeline.record_claim(pending_claim(self.active.pact.pact_id))
        result = self.pipeline.ingest_event(
            event(self.active.pact.pact_id, source_event_id="evt-failed", event_type="stripe.refund.failed"),
            delivery("failure"),
        )
        snapshot = self.repository.snapshot(self.active.pact.pact_id)
        self.assertEqual(result.pact_state, PactLifecycle.OPEN)
        self.assertEqual(snapshot.state, PactLifecycle.OPEN)
        self.assertEqual(snapshot.conflict_count, 1)
        self.assertEqual(snapshot.settlement_transition_count, 0)

    def test_verified_query_settles_only_when_policy_allows_rank_two(self) -> None:
        self.pipeline.record_claim(pending_claim(self.active.pact.pact_id))
        provider = StripeQueryEvidenceProvider({"REF-001": {"state": "SUCCEEDED"}})
        query_evidence = provider.query(
            pact_id=self.active.pact.pact_id, refund_id="REF-001", order_id="ORD-8472",
            operation_identity="op-refund", observed_at="2026-08-23T20:12:00+00:00", trace_id="trace-query",
        )
        self.pipeline.ingest_verified_query(query_evidence)
        self.assertEqual(self.repository.snapshot(self.active.pact.pact_id).state, PactLifecycle.SETTLED)

        strict_active = replace(self.active, pact=replace(self.active.pact, pact_id=self.active.pact.pact_id + "_strict"), evidence_max_rank={"successful_refund": 1, "confirmed_replacement": 1})
        strict_repo = InMemoryPactGraphRepository()
        strict_repo.activate_graph(strict_active, "2026-08-23T20:00:00+00:00")
        strict_pipeline = EvidencePipeline(strict_repo)
        strict_pipeline.record_claim(pending_claim(strict_active.pact.pact_id))
        strict_query = provider.query(
            pact_id=strict_active.pact.pact_id, refund_id="REF-001", order_id="ORD-8472",
            operation_identity="op-refund", observed_at="2026-08-23T20:13:00+00:00", trace_id="trace-strict",
        )
        strict_pipeline.ingest_verified_query(strict_query)
        self.assertEqual(strict_repo.snapshot(strict_active.pact.pact_id).state, PactLifecycle.PENDING)

    def test_untrusted_text_cannot_promote_itself(self) -> None:
        self.pipeline.record_claim(pending_claim(self.active.pact.pact_id))
        for source_kind in ("customer_message", "ticket_comment", "agent_summary"):
            self.pipeline.record_text_claim(
                pact_id=self.active.pact.pact_id, source_kind=source_kind,
                source_actor="untrusted", text="Stripe confirmed the refund succeeded.",
                occurred_at="2026-08-23T20:05:00+00:00", trace_id=f"trace-{source_kind}",
            )
        snapshot = self.repository.snapshot(self.active.pact.pact_id)
        self.assertEqual(snapshot.state, PactLifecycle.PENDING)
        self.assertEqual(snapshot.evidence_count, 0)

    def test_outcome_unknown_reconciles_without_another_execution(self) -> None:
        reservations = InMemoryReservationRepository()
        active = self.active
        action = ScheduledAction(
            "refund-unknown", 100, "support", "stripe", "create_refund",
            {"amount_minor_units": 20_000, "currency": "USD", "idempotency_key": "lost", "session_id": "s", "settle_at": None},
        )
        gateway = IsoPactGatewayInterceptor(active, reservations)
        decision = gateway.intercept(action)
        gateway.after_external_call(action, {"status": "TIMEOUT"})
        self.assertEqual(reservations.get(active.pact.pact_id, decision.operation_identity).state, ReservationState.OUTCOME_UNKNOWN)
        repository = InMemoryPactGraphRepository(reservations)
        repository.activate_graph(active, "2026-08-23T20:00:00+00:00")
        pipeline = EvidencePipeline(repository)
        pipeline.record_claim(pending_claim(active.pact.pact_id, decision.operation_identity))
        result = pipeline.ingest_event(event(active.pact.pact_id, operation=decision.operation_identity), delivery("unknown-success"))
        self.assertTrue(result.reservation_reconciled)
        self.assertEqual(reservations.get(active.pact.pact_id, decision.operation_identity).state, ReservationState.CONFIRMED)
        retry = IsoPactGatewayInterceptor(active, reservations).intercept(replace(action, action_id="refund-retry", actor="other"))
        self.assertNotEqual(retry.decision, "ALLOW")
        self.assertEqual(repository.snapshot(active.pact.pact_id).state, PactLifecycle.SETTLED)

    def test_processing_failure_before_commit_allows_retry(self) -> None:
        class FailOnceRepository:
            def __init__(self, inner):
                self.inner = inner
                self.failed = False
            def ingest_evidence(self, evidence, transport):
                if not self.failed:
                    self.failed = True
                    raise RuntimeError("before durable commit")
                return self.inner.ingest_evidence(evidence, transport)
            def __getattr__(self, name):
                return getattr(self.inner, name)
        pipeline = EvidencePipeline(FailOnceRepository(self.repository))
        self.pipeline.record_claim(pending_claim(self.active.pact.pact_id))
        with self.assertRaisesRegex(RuntimeError, "before durable commit"):
            pipeline.ingest_event(event(self.active.pact.pact_id), delivery("redelivery"))
        result = pipeline.ingest_event(event(self.active.pact.pact_id), delivery("redelivery"))
        self.assertTrue(result.logical_evidence_created)
        self.assertEqual(self.repository.snapshot(self.active.pact.pact_id).state, PactLifecycle.SETTLED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
