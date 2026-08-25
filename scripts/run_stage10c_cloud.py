from __future__ import annotations

import argparse
import json
import runpy
import sys
import time

from google.cloud import firestore, pubsub_v1

from isopact.evidence.firestore import FirestorePactGraphRepository
from isopact.evidence.pipeline import EvidencePipeline
from isopact.evidence.pubsub import process_received_message
from isopact.invariants.engine import CommerceInvariantEngine
from isopact.invariants.scenarios import NOW, protected_events, protected_facts, stage6_policy
from isopact.observability import telemetry


def run(path: str, argv: list[str]) -> None:
    previous = sys.argv
    try:
        sys.argv = [path, *argv]
        runpy.run_path(path, run_name="__main__")
    finally:
        sys.argv = previous


def replay_existing_evidence(project: str, pact_id: str) -> None:
    db = firestore.Client(project=project)
    ref = db.collection("pacts").document(pact_id)
    evidence_docs = [doc.to_dict() for doc in ref.collection("evidence").stream()]
    authoritative = next(item for item in evidence_docs if int(item["evidence_rank"]) == 1)
    EvidencePipeline(FirestorePactGraphRepository(project, client=db)).ingest_event({
        "event_type": authoritative["evidence_type"],
        "source_system": authoritative["source_system"],
        "source_event_id": authoritative["source_event_id"],
        "pact_id": pact_id,
        "subject": authoritative["subject"],
        "external_object_id": authoritative.get("external_object_id"),
        "operation_identity": authoritative.get("operation_identity"),
        "operation_attempt": authoritative.get("operation_attempt", 1),
        "source_sequence": authoritative.get("source_sequence"),
        "occurred_at": authoritative["occurred_at"],
        "ingested_at": authoritative["ingested_at"],
        "trace_id": authoritative.get("trace_id"),
    })


def prove_pubsub_link(project: str, pact_id: str, topic_id: str, subscription_id: str) -> None:
    """Publish and consume a real duplicate evidence delivery with a span link."""
    db = firestore.Client(project=project)
    ref = db.collection("pacts").document(pact_id)
    authoritative = next(
        item for item in (doc.to_dict() for doc in ref.collection("evidence").stream())
        if int(item["evidence_rank"]) == 1
    )
    payload = {
        "event_type": authoritative["evidence_type"],
        "source_system": authoritative["source_system"],
        "source_event_id": authoritative["source_event_id"],
        "pact_id": pact_id,
        "subject": authoritative["subject"],
        "external_object_id": authoritative.get("external_object_id"),
        "operation_identity": authoritative.get("operation_identity"),
        "operation_attempt": authoritative.get("operation_attempt", 1),
        "source_sequence": authoritative.get("source_sequence"),
        "occurred_at": authoritative["occurred_at"],
        "ingested_at": authoritative["ingested_at"],
        "trace_id": authoritative.get("trace_id"),
    }
    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()
    topic = publisher.topic_path(project, topic_id)
    subscription = subscriber.subscription_path(project, subscription_id)
    attributes = {"isopact_proof": "stage10c-span-link"}
    with telemetry.span("isopact.agent.invoke", **{"isopact.pact_id": pact_id}):
        telemetry.inject(attributes)
        message_id = publisher.publish(
            topic, json.dumps(payload, sort_keys=True).encode(), **attributes
        ).result(timeout=60)
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        response = subscriber.pull(
            request={"subscription": subscription, "max_messages": 10}, timeout=20
        )
        for received in response.received_messages:
            if received.message.message_id == message_id:
                process_received_message(
                    EvidencePipeline(FirestorePactGraphRepository(project, client=db)),
                    received,
                )
                subscriber.acknowledge(
                    request={"subscription": subscription, "ack_ids": [received.ack_id]}
                )
                telemetry.log(
                    "INFO",
                    "asynchronous evidence linked",
                    **{
                        "isopact.pact_id": pact_id,
                        "isopact.pubsub.message_id": message_id,
                        "isopact.source_event_id": authoritative["source_event_id"],
                    },
                )
                return
            subscriber.modify_ack_deadline(
                request={
                    "subscription": subscription,
                    "ack_ids": [received.ack_id],
                    "ack_deadline_seconds": 0,
                }
            )
    raise TimeoutError(f"Pub/Sub proof message not received: {message_id}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--primary-pact", required=True)
    parser.add_argument("--signer-service-account", required=True)
    parser.add_argument("--key-version-1", required=True)
    parser.add_argument("--key-version-2", required=True)
    parser.add_argument("--topic", default="isopact-stage5-evidence")
    parser.add_argument("--subscription", default="isopact-stage5-evidence-proof")
    parser.add_argument("--skip-pubsub-link", action="store_true")
    args = parser.parse_args()
    replay_existing_evidence(args.project, args.primary_pact)
    if not args.skip_pubsub_link:
        prove_pubsub_link(args.project, args.primary_pact, args.topic, args.subscription)
    facts = protected_facts(settled=True)
    CommerceInvariantEngine().evaluate(
        pact_id=args.primary_pact, graph_revision=10, facts=facts,
        policy=stage6_policy(), selected_resolution="successful_refund",
        settlement_evidence_satisfied=True, ticket_closed=True,
        agent_complete=True, protection_events=protected_events(facts),
        evaluated_at=NOW,
    )
    run("/app/scripts/prove_resolver.py", ["--project", args.project, "--runs", "1"])
    with telemetry.span("isopact.external.replacement", **{"isopact.pact_id": args.primary_pact, "isopact.external.executed": False, "isopact.reason_code": "EXCLUSIVE_RESOLUTION_CONFLICT"}):
        pass
    try:
        run("/app/scripts/prove_stage9_signed_settlement.py", [
            "--project", args.project, "--pact-id", args.primary_pact,
            "--signer-service-account", args.signer_service_account,
            "--key-version-1", args.key_version_1, "--key-version-2", args.key_version_2,
        ])
    except Exception as exc:
        if type(exc).__name__ != "AlreadyExists":
            raise
        telemetry.log("WARNING", "signed proof already persisted; live signing execution retained", error_type=type(exc).__name__)
    finally:
        telemetry.flush()
        time.sleep(8)


if __name__ == "__main__":
    main()
