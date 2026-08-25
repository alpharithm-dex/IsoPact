from __future__ import annotations

import json
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

PROJECT = "isopact-agentic-20260823"
REGION = "europe-west1"
RESOURCES = {
    "SUPPORT": "projects/442539309409/locations/europe-west1/reasoningEngines/1997126532413259776",
    "FULFILLMENT": "projects/442539309409/locations/europe-west1/reasoningEngines/7471674091947163648",
    "RETENTION": "projects/442539309409/locations/europe-west1/reasoningEngines/1103584218845282304",
    "RESOLVER": "projects/442539309409/locations/europe-west1/reasoningEngines/4435825730634383360",
}


def write(name: str, value: Any) -> None:
    path = ROOT / "artifacts" / "agents" / name
    path.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: sanitize(item) for key, item in value.items() if key != "thought_signature"}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value


def tool_response(events: list[dict], name: str) -> dict:
    for event in events:
        for part in event.get("content", {}).get("parts", []):
            response = part.get("function_response", {})
            if response.get("name") == name:
                return response.get("response", {})
    raise RuntimeError(f"missing {name} function response")


def final_text(events: list[dict]) -> str:
    texts = []
    for event in events:
        for part in event.get("content", {}).get("parts", []):
            if part.get("text"):
                texts.append(str(part["text"]))
    return texts[-1] if texts else ""


def invocation_ids(events: list[dict]) -> list[str]:
    return sorted({str(event["invocation_id"]) for event in events if event.get("invocation_id")})


def invoke(role: str, prompt: str, user_id: str) -> dict:
    from vertexai import agent_engines
    from google.api_core.exceptions import NotFound

    remote = agent_engines.get(RESOURCES[role])
    try:
        events = [sanitize(item) for item in remote.stream_query(message=prompt, user_id=user_id)]
    except NotFound:
        # Current Agent Platform resources can remain available through the
        # documented REST streamQuery surface while the legacy gRPC execution
        # client returns a control-plane 404. Preserve the same live resource
        # and method; only the transport changes.
        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        resource = RESOURCES[role]
        url = f"https://{REGION}-aiplatform.googleapis.com/v1/{resource}:streamQuery"
        response = AuthorizedSession(credentials).post(
            url,
            json={
                "classMethod": "stream_query",
                "input": {"message": prompt, "user_id": user_id},
            },
            timeout=180,
        )
        response.raise_for_status()
        events = [
            sanitize(json.loads(line))
            for line in response.text.splitlines()
            if line.strip()
        ]
    return {
        "role": role,
        "resource": RESOURCES[role],
        "user_id": user_id,
        "invocation_ids": invocation_ids(events),
        "events": events,
        "final_text": final_text(events),
        "errors": [item for item in events if item.get("error_code")],
    }


def activate(namespace: str, client):
    from isopact.evidence.firestore import FirestorePactGraphRepository
    from isopact.evidence.pipeline import utc_now
    from isopact.reservations.firestore import FirestoreReservationRepository
    from prove_agent_fleet import active_pact

    active = active_pact(namespace)
    FirestoreReservationRepository(PROJECT, client=client).activate(active.pact.pact_id, active.to_document())
    FirestorePactGraphRepository(PROJECT, client=client).activate_graph(active, utc_now())
    return active


def external_objects(client, pact_id: str) -> list[dict]:
    return [item.to_dict() for item in client.collection("pacts").document(pact_id).collection("external_objects").stream()]


def response_summary(invocation: dict, tool_name: str) -> dict:
    response = tool_response(invocation["events"], tool_name)
    return {
        "role": invocation["role"],
        "resource": invocation["resource"],
        "user_id": invocation["user_id"],
        "invocation_ids": invocation["invocation_ids"],
        "gateway": response,
        "agent_statement": invocation["final_text"],
        "errors": invocation["errors"],
    }


def main() -> int:
    import requests
    import vertexai
    from google.cloud import firestore
    from isopact.evidence.firestore import FirestorePactGraphRepository
    from isopact.evidence.pipeline import EvidencePipeline, utc_now

    generated = datetime.now(UTC)
    stamp = generated.strftime("%Y%m%d%H%M%S")
    client = firestore.Client(project=PROJECT)
    vertexai.init(project=PROJECT, location=REGION)
    gateway_url = "https://isopact-outcome-gateway-442539309409.africa-south1.run.app"

    invalid = requests.post(
        f"{gateway_url}/v1/pacts/not-a-real-pact/actions/refund",
        headers={"Authorization": "Bearer invalid-stage8b-token"},
        json={"agent_id": "isopact-support-v1"}, timeout=20,
    )
    try:
        invalid_body = invalid.json()
    except ValueError:
        invalid_body = {"error": "REJECTED_AT_CLOUD_RUN_IAM", "body_stored": False}
    invalid_identity = {
        "http_status": invalid.status_code,
        "response": invalid_body,
        "proof": "body identity cannot substitute for a signed runtime token",
    }

    race_pact = activate(f"stage8b-race-{stamp}", client)
    race_prompts = {
        "SUPPORT": (
            f"Call request_refund_through_isopact exactly once for pact_id={race_pact.pact.pact_id}, "
            "order_id=ORD-8472, session_id=stage8b-race-support, trace_id=trace-stage8b-race-support, "
            "request_id=req-stage8b-race-support, amount_minor_units=20000. Report the exact result."
        ),
        "FULFILLMENT": (
            f"Call request_replacement_through_isopact exactly once for pact_id={race_pact.pact.pact_id}, "
            "order_id=ORD-8472, session_id=stage8b-race-fulfillment, trace_id=trace-stage8b-race-fulfillment, "
            "request_id=req-stage8b-race-fulfillment. Report the exact result."
        ),
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        support_future = pool.submit(invoke, "SUPPORT", race_prompts["SUPPORT"], "stage8b-race-support-user")
        fulfillment_future = pool.submit(invoke, "FULFILLMENT", race_prompts["FULFILLMENT"], "stage8b-race-fulfillment-user")
        support_race = response_summary(support_future.result(), "request_refund_through_isopact")
        fulfillment_race = response_summary(fulfillment_future.result(), "request_replacement_through_isopact")
    race = {
        "pact_id": race_pact.pact.pact_id,
        "schedule": "two actual remote Agent Runtime stream_query calls submitted concurrently",
        "support": support_race,
        "fulfillment": fulfillment_race,
        "external_objects": external_objects(client, race_pact.pact.pact_id),
    }
    race["external_primary_execution_count"] = len([x for x in race["external_objects"] if x["kind"] in {"refund", "replacement"}])
    write("stage8b-concurrent-primary-race.json", race)

    duplicate_pact = activate(f"stage8b-duplicate-{stamp}", client)
    def support_prompt(session: str, request_id: str) -> str:
        return (
            f"Call request_refund_through_isopact exactly once for pact_id={duplicate_pact.pact.pact_id}, "
            f"order_id=ORD-8472, session_id={session}, trace_id=trace-{session}, request_id={request_id}, "
            "amount_minor_units=20000. Report the exact result."
        )
    session_a = response_summary(invoke("SUPPORT", support_prompt("stage8b-dup-a", "req-stage8b-dup-a"), "stage8b-dup-user-a"), "request_refund_through_isopact")
    session_b = response_summary(invoke("SUPPORT", support_prompt("stage8b-dup-b", "req-stage8b-dup-b"), "stage8b-dup-user-b"), "request_refund_through_isopact")
    duplicate = {
        "pact_id": duplicate_pact.pact.pact_id,
        "session_a": session_a,
        "session_b": session_b,
        "external_objects": external_objects(client, duplicate_pact.pact.pact_id),
    }
    duplicate["external_refund_execution_count"] = len([x for x in duplicate["external_objects"] if x["kind"] == "refund"])
    write("stage8b-duplicate-support-sessions.json", duplicate)

    e2e_pact = activate(f"stage8b-e2e-{stamp}", client)
    support_e2e_prompt = (
        f"Call request_refund_through_isopact exactly once for pact_id={e2e_pact.pact.pact_id}, order_id=ORD-8472, "
        "session_id=stage8b-e2e-support, trace_id=trace-stage8b-e2e-support, request_id=req-stage8b-e2e-support, "
        "amount_minor_units=20000, body_agent_id=isopact-resolver-v1. Report the verified caller and exact result."
    )
    support_e2e_raw = invoke("SUPPORT", support_e2e_prompt, "stage8b-e2e-support-user")
    support_e2e = response_summary(support_e2e_raw, "request_refund_through_isopact")
    refund = support_e2e["gateway"]

    fulfillment_e2e = response_summary(invoke("FULFILLMENT", (
        f"Call request_replacement_through_isopact exactly once for pact_id={e2e_pact.pact.pact_id}, order_id=ORD-8472, "
        "session_id=stage8b-e2e-fulfillment, trace_id=trace-stage8b-e2e-fulfillment, request_id=req-stage8b-e2e-fulfillment. Report the exact result."
    ), "stage8b-e2e-fulfillment-user"), "request_replacement_through_isopact")
    retention_e2e = response_summary(invoke("RETENTION", (
        f"Call request_goodwill_through_isopact exactly once for pact_id={e2e_pact.pact.pact_id}, customer_id=CUS-104, "
        "session_id=stage8b-e2e-retention, trace_id=trace-stage8b-e2e-retention, request_id=req-stage8b-e2e-retention, "
        "amount_minor_units=5000. Report the exact result."
    ), "stage8b-e2e-retention-user"), "request_goodwill_through_isopact")
    duplicate_support_e2e = response_summary(invoke("SUPPORT", (
        f"Call request_refund_through_isopact exactly once for pact_id={e2e_pact.pact.pact_id}, order_id=ORD-8472, "
        "session_id=stage8b-e2e-support-second, trace_id=trace-stage8b-e2e-support-second, "
        "request_id=req-stage8b-e2e-support-second, amount_minor_units=20000. Report the exact result."
    ), "stage8b-e2e-support-second-user"), "request_refund_through_isopact")
    resolver_e2e = response_summary(invoke("RESOLVER", (
        f"For pact_id={e2e_pact.pact.pact_id}, call request_validated_resolution_plan exactly once with "
        "selected_registry_action_ids=[carrier_cancel_unaccepted_label_v1], session_id=stage8b-e2e-resolver, "
        "trace_id=trace-stage8b-e2e-resolver, request_id=req-stage8b-e2e-resolver. Report that execution was not performed."
    ), "stage8b-e2e-resolver-user"), "request_validated_resolution_plan")

    graph = FirestorePactGraphRepository(PROJECT, client=client)
    pipeline = EvidencePipeline(graph)
    statement_time = utc_now()
    pipeline.record_text_claim(
        pact_id=e2e_pact.pact.pact_id, source_kind="agent", source_actor="isopact-support-v1",
        text=support_e2e_raw["final_text"], occurred_at=statement_time,
        trace_id="trace-stage8b-e2e-support-statement",
    )
    before_evidence = graph.snapshot(e2e_pact.pact.pact_id)
    authoritative = pipeline.ingest_event({
        "pact_id": e2e_pact.pact.pact_id,
        "source_system": "stripe",
        "source_event_id": f"evt-stage8b-{stamp}",
        "event_type": "stripe.refund.succeeded",
        "subject": "ORD-8472",
        "external_object_id": refund["external_object"]["external_object_id"],
        "operation_identity": refund["operation_identity"],
        "operation_attempt": 1,
        "occurred_at": utc_now(),
        "trace_id": "trace-stage8b-e2e-stripe",
    })
    after_evidence = graph.snapshot(e2e_pact.pact.pact_id)
    e2e = {
        "pact_id": e2e_pact.pact.pact_id,
        "support": support_e2e,
        "body_spoof_proof": {
            "supplied": refund.get("body_agent_id_supplied"),
            "verified": refund.get("verified_agent_id"),
            "body_identity_used_for_authority": refund.get("body_identity_used_for_authority"),
        },
        "fulfillment": fulfillment_e2e,
        "retention": retention_e2e,
        "duplicate_support": duplicate_support_e2e,
        "resolver": resolver_e2e,
        "agent_rank4_statement": support_e2e_raw["final_text"],
        "before_authoritative_evidence": asdict(before_evidence),
        "authoritative_evidence_result": asdict(authoritative),
        "after_authoritative_evidence": asdict(after_evidence),
        "external_objects": external_objects(client, e2e_pact.pact.pact_id),
    }
    write("stage8b-end-to-end.json", e2e)
    write("stage8b-agent-claim-vs-evidence.json", {
        "pact_id": e2e_pact.pact.pact_id,
        "rank4_statement": support_e2e_raw["final_text"],
        "state_after_rank4": before_evidence.state.value,
        "rank1_event": "stripe.refund.succeeded",
        "state_after_rank1": after_evidence.state.value,
    })
    write("stage8b-identity-negative-tests.json", {"invalid_token": invalid_identity, "body_spoof": e2e["body_spoof_proof"]})

    responses = [support_race["gateway"], fulfillment_race["gateway"], session_a["gateway"], session_b["gateway"], support_e2e["gateway"], fulfillment_e2e["gateway"], retention_e2e["gateway"], duplicate_support_e2e["gateway"]]
    latencies = sorted(float(item["cross_region_round_trip_ms"]) for item in responses)
    percentile_95 = latencies[min(len(latencies) - 1, int(0.95 * (len(latencies) - 1)))]
    summary = {
        "generated_at": generated.isoformat(),
        "gateway_url": gateway_url,
        "gateway_region": "africa-south1",
        "firestore_region": "africa-south1",
        "agent_runtime_region": REGION,
        "invalid_identity_rejected": invalid.status_code == 401,
        "race_one_primary_external_execution": race["external_primary_execution_count"] == 1,
        "duplicate_one_refund_external_execution": duplicate["external_refund_execution_count"] == 1,
        "body_spoof_ignored": e2e["body_spoof_proof"]["body_identity_used_for_authority"] is False,
        "settled_only_after_rank1": before_evidence.state.value != "SETTLED" and after_evidence.state.value == "SETTLED",
        "end_to_end_duplicate_blocked": duplicate_support_e2e["gateway"].get("reason_code") == "DUPLICATE_OPERATION",
        "latency_ms": {"samples": latencies, "p50": statistics.median(latencies), "p95_nearest_rank": percentile_95},
        "pacts": {"race": race_pact.pact.pact_id, "duplicate": duplicate_pact.pact.pact_id, "end_to_end": e2e_pact.pact.pact_id},
    }
    write("stage8b-live-summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if all(summary[key] for key in ("invalid_identity_rejected", "race_one_primary_external_execution", "duplicate_one_refund_external_execution", "body_spoof_ignored", "settled_only_after_rank1", "end_to_end_duplicate_blocked")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
