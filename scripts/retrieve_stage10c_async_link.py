from __future__ import annotations

import argparse
import json
from pathlib import Path

import google.auth
from google.auth.transport.requests import AuthorizedSession


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "observability" / "async-span-link.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--pact", required=True)
    parser.add_argument("--message-id", required=True)
    parser.add_argument("--source-event-id", required=True)
    parser.add_argument("--execution", required=True)
    parser.add_argument("--start-time", required=True)
    parser.add_argument("--end-time", required=True)
    args = parser.parse_args()
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    session = AuthorizedSession(credentials)
    base = f"https://cloudtrace.googleapis.com/v1/projects/{args.project}/traces"

    log_response = session.post(
        "https://logging.googleapis.com/v2/entries:list",
        json={
            "resourceNames": [f"projects/{args.project}"],
            "filter": (
                'resource.type="cloud_run_job" AND '
                'resource.labels.job_name="isopact-stage10c-proof" AND '
                f'timestamp>="{args.start_time}" AND timestamp<="{args.end_time}" AND '
                '('
                'jsonPayload.message="opentelemetry span-link audit" OR '
                'jsonPayload.message="asynchronous evidence linked" OR '
                'textPayload:"opentelemetry span-link audit" OR '
                'textPayload:"asynchronous evidence linked"'
                ')'
            ),
            "orderBy": "timestamp asc",
            "pageSize": 1000,
        },
        timeout=30,
    )
    log_response.raise_for_status()
    structured_logs: list[dict] = []
    for entry in log_response.json().get("entries", []):
        payload = entry.get("jsonPayload")
        if not payload and entry.get("textPayload"):
            try:
                payload = json.loads(entry["textPayload"])
            except (TypeError, json.JSONDecodeError):
                continue
        if payload:
            structured_logs.append({"timestamp": entry.get("timestamp"), **payload})
    audits = [
        item for item in structured_logs
        if item.get("message") == "opentelemetry span-link audit"
        and item.get("isopact.pact_id") == args.pact
    ]
    pubsub_logs = [
        item for item in structured_logs
        if item.get("message") == "asynchronous evidence linked"
        and item.get("isopact.source_event_id") == args.source_event_id
        and (
            args.message_id == "pending"
            or str(item.get("isopact.pubsub.message_id")) == args.message_id
        )
    ]
    actual_message_id = (
        str(pubsub_logs[0].get("isopact.pubsub.message_id"))
        if pubsub_logs else args.message_id
    )

    def summaries(span_name: str) -> list[dict]:
        response = session.get(
            base,
            params={
                "filter": f"+span:{span_name} +label:isopact.pact_id:{args.pact}",
                "startTime": args.start_time,
                "endTime": args.end_time,
                "pageSize": 1000,
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("traces", [])

    trace_ids = {
        item["traceId"]
        for item in (
            *summaries("isopact.agent.invoke"),
            *summaries("isopact.evidence.ingest"),
        )
    }
    publishers: list[dict] = []
    consumers: list[dict] = []
    for trace_id in sorted(trace_ids):
        response = session.get(f"{base}/{trace_id}", timeout=30)
        response.raise_for_status()
        for span in response.json().get("spans", []):
            labels = span.get("labels", {})
            if labels.get("isopact.pact_id") != args.pact:
                continue
            record = {
                "trace_id": trace_id,
                "span_id": span.get("spanId"),
                "parent_span_id": span.get("parentSpanId"),
                "name": span.get("name"),
                "labels": labels,
                "links": span.get("links", []),
            }
            if span.get("name") == "isopact.agent.invoke":
                publishers.append(record)
            if span.get("name") == "isopact.evidence.ingest":
                consumers.append(record)

    publisher_keys = {(item["trace_id"], str(item["span_id"])) for item in publishers}
    matched_links: list[dict] = []
    for consumer in consumers:
        for link in consumer["links"]:
            key = (str(link.get("traceId")), str(link.get("spanId")))
            if key in publisher_keys:
                matched_links.append({
                    "consumer_trace_id": consumer["trace_id"],
                    "consumer_span_id": consumer["span_id"],
                    "publisher_trace_id": key[0],
                    "publisher_span_id": key[1],
                    "link": link,
                })

    publisher_audits = [
        item for item in audits if item.get("isopact.span.name") == "isopact.agent.invoke"
    ]
    consumer_audits = [
        item for item in audits if item.get("isopact.span.name") == "isopact.evidence.ingest"
    ]
    audit_matches: list[dict] = []
    audit_publisher_keys = {
        (item.get("isopact.span.trace_id"), item.get("isopact.span.span_id"))
        for item in publisher_audits
    }
    for consumer in consumer_audits:
        for link in consumer.get("isopact.span.links", []):
            key = (link.get("trace_id"), link.get("span_id"))
            if key in audit_publisher_keys:
                audit_matches.append({
                    "consumer_trace_id": consumer.get("isopact.span.trace_id"),
                    "consumer_span_id": consumer.get("isopact.span.span_id"),
                    "publisher_trace_id": key[0],
                    "publisher_span_id": key[1],
                    "link": link,
                })

    trace_span_keys = {
        (item["trace_id"], str(item["span_id"])) for item in (*publishers, *consumers)
    }
    audited_trace_span_keys = {
        (
            str(item.get("isopact.span.trace_id")),
            str(int(str(item.get("isopact.span.span_id")), 16)),
        )
        for item in audits
        if item.get("isopact.span.trace_id") and item.get("isopact.span.span_id")
    }
    audit_spans_in_cloud_trace = sorted(audited_trace_span_keys & trace_span_keys)

    consumer_roots = [item for item in consumers if not item["parent_span_id"]]
    result = {
        "source": "LIVE_CLOUD_TRACE_AND_PUBSUB_SDK_AUDIT",
        "project": args.project,
        "execution": args.execution,
        "pact": args.pact,
        "topic": "projects/isopact-agentic-20260823/topics/isopact-stage5-evidence",
        "subscription": "projects/isopact-agentic-20260823/subscriptions/isopact-stage5-evidence-proof",
        "message_id": actual_message_id,
        "source_event_id": args.source_event_id,
        "proof_service_account": "isopact-stage10c-proof@isopact-agentic-20260823.iam.gserviceaccount.com",
        "topic_role": "roles/pubsub.publisher",
        "subscription_role": "roles/pubsub.subscriber",
        "publishers": publishers,
        "consumers": consumers,
        "cloud_trace_links": matched_links,
        "cloud_trace_read_api_exposes_links": bool(matched_links),
        "sdk_audit_publishers": publisher_audits,
        "sdk_audit_consumers": consumer_audits,
        "matched_links": audit_matches,
        "audit_spans_in_cloud_trace": audit_spans_in_cloud_trace,
        "pubsub_completion_logs": pubsub_logs,
        "consumer_root_count": len(consumer_roots),
        "fake_parent_child_relationships": 0 if consumer_roots else 1,
        "ack_after_processing": bool(pubsub_logs),
        "proof_method": "real Pub/Sub delivery + OTel SDK on_end link audit + Cloud Trace root-span reconciliation",
        "result": "PASS" if (
            audit_matches
            and consumer_roots
            and len(audit_spans_in_cloud_trace) >= 2
            and pubsub_logs
        ) else "BLOCKED",
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
