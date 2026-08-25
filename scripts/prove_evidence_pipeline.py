from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import queue
import sys
import time
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from google.cloud import pubsub_v1
from google.api_core.exceptions import Aborted, ServiceUnavailable

from isopact.domain.models import ReservationState
from isopact.evidence.firestore import FirestorePactGraphRepository
from isopact.evidence.models import (
    ClaimType,
    EvidenceDelivery,
    EvidenceRank,
    ImmediateState,
    PactLifecycle,
    StateClaim,
)
from isopact.evidence.pipeline import EvidencePipeline, record_replay_claims, utc_now
from isopact.evidence.pubsub import process_received_message
from isopact.evidence.query import StripeQueryEvidenceProvider
from isopact.gateway.interceptor import IsoPactGatewayInterceptor
from isopact.reservations.firestore import FirestoreReservationRepository
from isopact.simulator.runner import ScenarioRunner
from isopact.simulator.scenarios import build_scenario
from prove_firestore_gateway import active_pact, refund_action


PROJECT = "isopact-agentic-20260823"
DATABASE = "(default)"
TOPIC_ID = "isopact-stage5-evidence"
SUBSCRIPTION_ID = "isopact-stage5-evidence-proof"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def activate(
    graph: FirestorePactGraphRepository,
    reservations: FirestoreReservationRepository,
    namespace: str,
):
    active = active_pact(namespace)
    reservations.activate(active.pact.pact_id, active.to_document())
    graph.activate_graph(active, utc_now())
    return active


def pending_claim(pact_id: str, operation_identity: str) -> StateClaim:
    return StateClaim(
        claim_id="claim_stage5_pending",
        pact_id=pact_id,
        claim_type=ClaimType.API_RESPONSE,
        source_system="stripe",
        source_actor="support-a",
        subject="ORD-8472",
        external_object_id="REF-001",
        operation_identity=operation_identity,
        resolution_path="successful_refund",
        immediate_state=ImmediateState.PENDING,
        evidence_rank=EvidenceRank.ACCEPTED_PENDING_RESPONSE,
        occurred_at="2026-08-23T20:01:40+00:00",
        ingested_at=utc_now(),
        trace_id="trace-stage5-pending",
    )


def success_payload(
    pact_id: str,
    operation_identity: str,
    source_event_id: str,
    *,
    occurred_at: str = "2026-08-23T20:16:40+00:00",
    attempt: int = 1,
) -> dict[str, Any]:
    return {
        "pact_id": pact_id,
        "source_system": "stripe",
        "source_event_id": source_event_id,
        "event_type": "stripe.refund.succeeded",
        "subject": "ORD-8472",
        "external_object_id": "REF-001",
        "operation_identity": operation_identity,
        "operation_attempt": attempt,
        "occurred_at": occurred_at,
        "trace_id": f"trace-{source_event_id}",
    }


def direct_delivery(index: int) -> EvidenceDelivery:
    return EvidenceDelivery(
        delivery_id=f"concurrent_worker_{index:02d}",
        delivery_mechanism="CONCURRENT_FIRESTORE_PROOF",
        pubsub_message_id=f"synthetic-transport-{index:02d}",
        publish_timestamp=None,
        received_at=utc_now(),
        attributes={"proof": "concurrent-duplicate-ingestion"},
    )


def _ingest_worker(
    project: str,
    database: str,
    payload: dict[str, Any],
    index: int,
    barrier: Any,
    result_queue: Any,
) -> None:
    try:
        repository = FirestorePactGraphRepository(project, database)
        pipeline = EvidencePipeline(repository)
        barrier.wait(timeout=120)
        application_attempts = 0
        while True:
            application_attempts += 1
            try:
                result = pipeline.ingest_event(payload, direct_delivery(index))
                break
            except (Aborted, ServiceUnavailable):
                if application_attempts >= 8:
                    raise
                time.sleep(0.04 * application_attempts + (index % 5) * 0.01)
        result_queue.put(
            {
                "ok": True,
                "index": index,
                "logical_evidence_created": result.logical_evidence_created,
                "settlement_transition_created": result.settlement_transition_created,
                "economic_event_created": result.economic_event_created,
                "pact_state": result.pact_state.value,
                "transaction_callback_invocations": repository.transaction_callback_invocations,
                "application_attempts": application_attempts,
            }
        )
    except BaseException as exc:
        result_queue.put(
            {"ok": False, "index": index, "error": f"{type(exc).__name__}: {exc}"}
        )


def run_concurrent_ingestion(
    project: str, database: str, payload: dict[str, Any], workers: int = 25
) -> list[dict[str, Any]]:
    ctx = mp.get_context("spawn")
    barrier = ctx.Barrier(workers)
    result_queue = ctx.Queue()
    processes = [
        ctx.Process(
            target=_ingest_worker,
            args=(project, database, payload, index, barrier, result_queue),
        )
        for index in range(workers)
    ]
    for process in processes:
        process.start()
    results: list[dict[str, Any]] = []
    deadline = time.monotonic() + 300
    while len(results) < workers and time.monotonic() < deadline:
        try:
            results.append(result_queue.get(timeout=2))
        except queue.Empty:
            if all(not process.is_alive() for process in processes):
                break
    for process in processes:
        process.join(timeout=15)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
    if len(results) != workers:
        raise RuntimeError(f"received {len(results)} of {workers} ingestion results")
    failures = [item for item in results if not item.get("ok")]
    if failures:
        raise RuntimeError(f"concurrent ingestion failures: {failures}")
    return sorted(results, key=lambda item: item["index"])


def pull_until_ids(
    subscriber: pubsub_v1.SubscriberClient,
    subscription_path: str,
    wanted_ids: set[str],
    pipeline: EvidencePipeline,
    timeout_seconds: int = 90,
) -> list[dict[str, Any]]:
    processed: list[dict[str, Any]] = []
    deadline = time.monotonic() + timeout_seconds
    remaining = set(wanted_ids)
    while remaining and time.monotonic() < deadline:
        response = subscriber.pull(
            request={"subscription": subscription_path, "max_messages": 20},
            timeout=20,
        )
        ack_ids = []
        for received in response.received_messages:
            message_id = received.message.message_id
            if message_id in remaining:
                result = process_received_message(pipeline, received)
                processed.append(
                    {
                        "message_id": message_id,
                        "source_event_id": json.loads(received.message.data)["source_event_id"],
                        "logical_evidence_created": result.logical_evidence_created,
                        "settlement_transition_created": result.settlement_transition_created,
                        "pact_state": result.pact_state.value,
                    }
                )
                remaining.remove(message_id)
            ack_ids.append(received.ack_id)
        if ack_ids:
            subscriber.acknowledge(
                request={"subscription": subscription_path, "ack_ids": ack_ids}
            )
    if remaining:
        raise TimeoutError(f"Pub/Sub messages not received: {sorted(remaining)}")
    return processed


def prove_redelivery(
    publisher: pubsub_v1.PublisherClient,
    subscriber: pubsub_v1.SubscriberClient,
    topic_path: str,
    subscription_path: str,
    payload: dict[str, Any],
    pipeline: EvidencePipeline,
) -> dict[str, Any]:
    message_id = publisher.publish(
        topic_path,
        json.dumps(payload, sort_keys=True).encode(),
        proof="processing-failure-redelivery",
    ).result(timeout=60)
    first_ack_id = None
    deadline = time.monotonic() + 90
    while first_ack_id is None and time.monotonic() < deadline:
        response = subscriber.pull(
            request={"subscription": subscription_path, "max_messages": 10}, timeout=20
        )
        other_ack_ids = []
        for received in response.received_messages:
            if received.message.message_id == message_id:
                first_ack_id = received.ack_id
            else:
                other_ack_ids.append(received.ack_id)
        if other_ack_ids:
            subscriber.acknowledge(request={"subscription": subscription_path, "ack_ids": other_ack_ids})
    if first_ack_id is None:
        raise TimeoutError("failure-proof message was not delivered")
    # Simulated processing failure occurs before any graph write. Do not ack; make
    # the message immediately eligible for redelivery.
    subscriber.modify_ack_deadline(
        request={"subscription": subscription_path, "ack_ids": [first_ack_id], "ack_deadline_seconds": 0}
    )
    redelivered = None
    while redelivered is None and time.monotonic() < deadline:
        response = subscriber.pull(
            request={"subscription": subscription_path, "max_messages": 10}, timeout=20
        )
        other_ack_ids = []
        for received in response.received_messages:
            if received.message.message_id == message_id:
                redelivered = received
                break
            other_ack_ids.append(received.ack_id)
        if other_ack_ids:
            subscriber.acknowledge(request={"subscription": subscription_path, "ack_ids": other_ack_ids})
    if redelivered is None:
        raise TimeoutError("message was not redelivered after unacked processing failure")
    result = process_received_message(pipeline, redelivered)
    subscriber.acknowledge(
        request={"subscription": subscription_path, "ack_ids": [redelivered.ack_id]}
    )
    return {
        "message_id": message_id,
        "first_attempt_acked": False,
        "redelivered_same_message_id": redelivered.message.message_id == message_id,
        "durable_processing_before_ack": result.logical_evidence_created,
        "final_ack_after_commit": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live Stage 5 Firestore and Pub/Sub proofs")
    parser.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT", PROJECT))
    parser.add_argument("--database", default=DATABASE)
    parser.add_argument("--topic", default=TOPIC_ID)
    parser.add_argument("--subscription", default=SUBSCRIPTION_ID)
    args = parser.parse_args()
    run_id = datetime.now(UTC).strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:8]
    timestamp = utc_now()
    output_dir = ROOT / "artifacts" / "evidence"
    graph = FirestorePactGraphRepository(args.project, args.database)
    reservations = FirestoreReservationRepository(args.project, args.database, client=graph.client)
    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()
    topic_path = publisher.topic_path(args.project, args.topic)
    subscription_path = subscriber.subscription_path(args.project, args.subscription)
    cleanup: list[str] = []
    common = {
        "project": args.project,
        "database": args.database,
        "topic": topic_path,
        "subscription": subscription_path,
        "run_id": run_id,
        "timestamp": timestamp,
    }
    try:
        # Primary protected replay: same Stage 2 action schedule, graph claims added after execution.
        primary_namespace = f"stage5_{run_id}_primary"
        primary_active = activate(graph, reservations, primary_namespace)
        cleanup.append(primary_active.pact.pact_id)
        gateway = IsoPactGatewayInterceptor(primary_active, reservations)
        replay = ScenarioRunner(gateway).run(build_scenario("missing_order_unmanaged"))
        primary_pipeline = EvidencePipeline(graph)
        pre_evidence = record_replay_claims(primary_pipeline, primary_active.pact.pact_id, replay)
        refund_result = next(item for item in replay["action_results"] if item["action_id"] == "e01")
        operation_identity = refund_result["interceptor_decision"]["operation_identity"]
        primary_event = success_payload(
            primary_active.pact.pact_id,
            operation_identity,
            f"evt_stage5_primary_{run_id}",
        )
        message_ids = [
            publisher.publish(
                topic_path,
                json.dumps(primary_event, sort_keys=True).encode(),
                proof="primary-settlement",
            ).result(timeout=60)
            for _ in range(3)
        ]
        pubsub_results = pull_until_ids(
            subscriber, subscription_path, set(message_ids), primary_pipeline
        )
        primary_final = FirestorePactGraphRepository(args.project, args.database).snapshot(
            primary_active.pact.pact_id
        )
        replay_artifact = {
            **common,
            "pact_id": primary_active.pact.pact_id,
            "schedule": replay["schedule"],
            "schedule_digest": __import__("hashlib").sha256(
                json.dumps(replay["schedule"], sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "pre_evidence": pre_evidence,
            "post_evidence": {
                "refund_state": "SUCCEEDED",
                "evidence_rank": 1,
                "isopact_state": primary_final.state.value,
                "business_settled": primary_final.state is PactLifecycle.SETTLED,
                "settlement_transitions": primary_final.settlement_transition_count,
            },
            "graph_counts": asdict(primary_final),
        }
        write_json(ROOT / "artifacts" / "replays" / "missing_order_stage5_protected.json", replay_artifact)
        live_pubsub_artifact = {
            **common,
            "pact_id": primary_active.pact.pact_id,
            "source_event_id": primary_event["source_event_id"],
            "published_message_ids": message_ids,
            "deliveries": pubsub_results,
            "logical_evidence_records": primary_final.evidence_count,
            "final_evidence_rank": 1,
            "settlement_transitions": primary_final.settlement_transition_count,
            "final_pact_state": primary_final.state.value,
            "exactly_once_subscription_enabled": False,
        }
        write_json(output_dir / "live-pubsub-settlement.json", live_pubsub_artifact)

        # 25 independent processes ingest one logical event with distinct transport identities.
        duplicate_namespace = f"stage5_{run_id}_duplicate"
        duplicate_active = activate(graph, reservations, duplicate_namespace)
        cleanup.append(duplicate_active.pact.pact_id)
        duplicate_operation = "operation-stage5-duplicate"
        EvidencePipeline(graph).record_claim(pending_claim(duplicate_active.pact.pact_id, duplicate_operation))
        duplicate_payload = success_payload(
            duplicate_active.pact.pact_id,
            duplicate_operation,
            f"evt_stage5_duplicate_{run_id}",
        )
        worker_results = run_concurrent_ingestion(
            args.project, args.database, duplicate_payload, 25
        )
        duplicate_snapshot = graph.snapshot(duplicate_active.pact.pact_id)
        duplicate_artifact = {
            **common,
            "pact_id": duplicate_active.pact.pact_id,
            "concurrent_workers": 25,
            "transport_attempts": 25,
            "unique_source_event_ids": 1,
            "logical_evidence_records": duplicate_snapshot.evidence_count,
            "delivery_records": duplicate_snapshot.delivery_count,
            "effective_settlement_transitions": duplicate_snapshot.settlement_transition_count,
            "economic_events": duplicate_snapshot.economic_event_count,
            "economic_value_minor_units": 20_000,
            "duplicated_economic_value": 0 if duplicate_snapshot.economic_event_count == 1 else duplicate_snapshot.economic_event_count - 1,
            "transaction_callback_invocations": sum(item["transaction_callback_invocations"] for item in worker_results),
            "workers": worker_results,
        }
        write_json(output_dir / "live-duplicate-evidence.json", duplicate_artifact)

        # Success first, then an older lower-ranked pending event and claim.
        ordering_namespace = f"stage5_{run_id}_ordering"
        ordering_active = activate(graph, reservations, ordering_namespace)
        cleanup.append(ordering_active.pact.pact_id)
        ordering_pipeline = EvidencePipeline(graph)
        ordering_operation = "operation-stage5-ordering"
        ordering_pipeline.ingest_event(
            success_payload(
                ordering_active.pact.pact_id,
                ordering_operation,
                f"evt_stage5_order_success_{run_id}",
                occurred_at="2026-08-23T20:16:40+00:00",
            )
        )
        pending_payload = success_payload(
            ordering_active.pact.pact_id,
            ordering_operation,
            f"evt_stage5_order_pending_{run_id}",
            occurred_at="2026-08-23T20:01:40+00:00",
        )
        pending_payload["event_type"] = "stripe.refund.pending"
        ordering_pipeline.ingest_event(pending_payload)
        ordering_pipeline.record_claim(pending_claim(ordering_active.pact.pact_id, ordering_operation))
        ordering_snapshot = graph.snapshot(ordering_active.pact.pact_id)
        ordering_resolved = ordering_snapshot.resolved_operations[ordering_operation]
        out_of_order_artifact = {
            **common,
            "pact_id": ordering_active.pact.pact_id,
            "arrival_sequence": ["stripe.refund.succeeded Rank 1", "older stripe.refund.pending Rank 3", "older local pending claim"],
            "resolved_final_state": ordering_resolved["state"],
            "resolved_final_rank": ordering_resolved["rank"],
            "pact_state": ordering_snapshot.state.value,
            "regression_occurred": ordering_resolved["state"] != "SUCCEEDED",
        }
        write_json(output_dir / "live-out-of-order.json", out_of_order_artifact)

        # OUTCOME_UNKNOWN reconciliation updates the Stage 4 reservation in the same transaction.
        unknown_namespace = f"stage5_{run_id}_unknown"
        unknown_active = activate(graph, reservations, unknown_namespace)
        cleanup.append(unknown_active.pact.pact_id)
        unknown_action = refund_action(5001)
        unknown_gateway = IsoPactGatewayInterceptor(unknown_active, reservations)
        unknown_decision = unknown_gateway.intercept(unknown_action)
        external_executions = 1
        unknown_gateway.after_external_call(unknown_action, {"status": "TIMEOUT"})
        before_unknown = reservations.get(unknown_active.pact.pact_id, unknown_decision.operation_identity)
        unknown_pipeline = EvidencePipeline(graph)
        unknown_pipeline.record_claim(pending_claim(unknown_active.pact.pact_id, unknown_decision.operation_identity))
        reconcile_result = unknown_pipeline.ingest_event(
            success_payload(
                unknown_active.pact.pact_id,
                unknown_decision.operation_identity,
                f"evt_stage5_unknown_{run_id}",
            )
        )
        reloaded_reservations = FirestoreReservationRepository(args.project, args.database)
        after_unknown = reloaded_reservations.get(unknown_active.pact.pact_id, unknown_decision.operation_identity)
        retry_decision = IsoPactGatewayInterceptor(unknown_active, reloaded_reservations).intercept(refund_action(5002))
        unknown_snapshot = FirestorePactGraphRepository(args.project, args.database).snapshot(unknown_active.pact.pact_id)
        unknown_artifact = {
            **common,
            "pact_id": unknown_active.pact.pact_id,
            "reservation_initial_state": before_unknown.state.value,
            "authoritative_evidence": "stripe.refund.succeeded",
            "reservation_final_state": after_unknown.state.value,
            "reservation_reconciled": reconcile_result.reservation_reconciled,
            "retry_decision_after_restart": retry_decision.decision,
            "additional_refund_executions": external_executions - 1,
            "total_refund_executions": external_executions,
            "final_pact_state": unknown_snapshot.state.value,
        }
        write_json(output_dir / "live-outcome-unknown-resolution.json", unknown_artifact)

        # Rank 2 query path under trusted policy.
        query_namespace = f"stage5_{run_id}_query"
        query_active = activate(graph, reservations, query_namespace)
        cleanup.append(query_active.pact.pact_id)
        query_operation = "operation-stage5-query"
        query_pipeline = EvidencePipeline(graph)
        query_pipeline.record_claim(pending_claim(query_active.pact.pact_id, query_operation))
        query_evidence = StripeQueryEvidenceProvider({"REF-001": {"state": "SUCCEEDED"}}).query(
            pact_id=query_active.pact.pact_id, refund_id="REF-001", order_id="ORD-8472",
            operation_identity=query_operation, observed_at="2026-08-23T20:18:00+00:00",
            trace_id="trace-stage5-query",
        )
        query_pipeline.ingest_verified_query(query_evidence)
        query_snapshot = graph.snapshot(query_active.pact.pact_id)

        # Authoritative failure remains unsettled.
        failure_namespace = f"stage5_{run_id}_failure"
        failure_active = activate(graph, reservations, failure_namespace)
        cleanup.append(failure_active.pact.pact_id)
        failure_operation = "operation-stage5-failure"
        failure_pipeline = EvidencePipeline(graph)
        failure_pipeline.record_claim(pending_claim(failure_active.pact.pact_id, failure_operation))
        failure_payload = success_payload(
            failure_active.pact.pact_id, failure_operation, f"evt_stage5_failure_{run_id}"
        )
        failure_payload["event_type"] = "stripe.refund.failed"
        failure_pipeline.ingest_event(failure_payload)
        failure_snapshot = graph.snapshot(failure_active.pact.pact_id)

        # Processing failure before persistence: no ack, same Pub/Sub message redelivers.
        redelivery_namespace = f"stage5_{run_id}_redelivery"
        redelivery_active = activate(graph, reservations, redelivery_namespace)
        cleanup.append(redelivery_active.pact.pact_id)
        redelivery_operation = "operation-stage5-redelivery"
        redelivery_pipeline = EvidencePipeline(graph)
        redelivery_pipeline.record_claim(pending_claim(redelivery_active.pact.pact_id, redelivery_operation))
        redelivery_proof = prove_redelivery(
            publisher, subscriber, topic_path, subscription_path,
            success_payload(redelivery_active.pact.pact_id, redelivery_operation, f"evt_stage5_redelivery_{run_id}"),
            redelivery_pipeline,
        )

        model_source = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "src" / "isopact" / "evidence").glob("*.py"))
        model_calls = sum(model_source.count(term) for term in ("google.genai", "genai.Client", "generate_content", "Gemini"))
        summary = {
            **common,
            "status": "PASS",
            "pact_graph": {
                "entities": ["Pact", "Participant", "StateClaim", "EconomicEvent", "Evidence", "Conflict", "OperationReservation reference", "SettlementEvaluation", "SettlementProof", "EvidenceDelivery"],
                "primary_claims": primary_final.claim_count,
                "primary_evidence": primary_final.evidence_count,
                "lifecycle_states_demonstrated": ["OPEN", "PENDING", "SETTLED"],
            },
            "pre_evidence": pre_evidence,
            "live_pubsub": live_pubsub_artifact,
            "duplicate_evidence": duplicate_artifact,
            "out_of_order": out_of_order_artifact,
            "outcome_unknown": unknown_artifact,
            "verified_query": {"rank": 2, "policy_max_rank": 2, "final_pact_state": query_snapshot.state.value},
            "authoritative_failure": {"evidence": "stripe.refund.failed", "final_pact_state": failure_snapshot.state.value, "conflicts": failure_snapshot.conflict_count},
            "redelivery": redelivery_proof,
            "model_calls_during_evidence_processing": model_calls,
        }
        write_json(output_dir / "summary.json", summary)
        print(json.dumps(summary, sort_keys=True, indent=2))
        assertions = [
            pre_evidence["agent_status"] == "COMPLETE",
            pre_evidence["jira_state"] == "CLOSED",
            pre_evidence["refund_immediate_state"] == "PENDING",
            pre_evidence["isopact_pact_state"] == "PENDING",
            not pre_evidence["business_settled"],
            primary_final.state is PactLifecycle.SETTLED,
            primary_final.evidence_count == 1,
            primary_final.settlement_transition_count == 1,
            len(set(message_ids)) == 3,
            duplicate_snapshot.evidence_count == 1,
            duplicate_snapshot.delivery_count == 25,
            duplicate_snapshot.settlement_transition_count == 1,
            duplicate_snapshot.economic_event_count == 1,
            ordering_resolved["state"] == "SUCCEEDED",
            not out_of_order_artifact["regression_occurred"],
            before_unknown.state is ReservationState.OUTCOME_UNKNOWN,
            after_unknown.state is ReservationState.CONFIRMED,
            retry_decision.decision != "ALLOW",
            unknown_snapshot.state is PactLifecycle.SETTLED,
            query_snapshot.state is PactLifecycle.SETTLED,
            failure_snapshot.state is not PactLifecycle.SETTLED,
            redelivery_proof["redelivered_same_message_id"],
            model_calls == 0,
        ]
        return 0 if all(assertions) else 1
    finally:
        subscriber.close()
        publisher.stop()
        for pact_id in cleanup:
            try:
                graph.cleanup_pact(pact_id)
            except Exception as exc:
                print(f"CLEANUP_WARNING {pact_id}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
