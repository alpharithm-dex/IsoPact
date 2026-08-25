from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import google.auth
from google.auth.transport.requests import AuthorizedSession
from google.cloud import firestore

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "observability"
SPAN_NAMES = (
    "isopact.gateway.request", "isopact.gateway.authenticate", "isopact.gateway.authorize",
    "isopact.reservation.transaction", "isopact.external.refund", "isopact.external.replacement",
    "isopact.external.goodwill", "isopact.evidence.ingest", "isopact.evidence.reduce",
    "isopact.invariants.evaluate", "isopact.settlement.evaluate", "isopact.resolver.reason",
    "isopact.resolution.validate", "isopact.compensation.precondition",
    "isopact.compensation.execute", "isopact.claim.append", "isopact.kms.checkpoint.sign",
    "isopact.kms.receipt.sign", "isopact.receipt.verify",
)
SCENARIO_SPANS = {
    "primary": (
        "isopact.gateway.request", "isopact.gateway.authenticate", "isopact.gateway.authorize",
        "isopact.reservation.transaction", "isopact.external.refund", "isopact.external.replacement", "isopact.external.goodwill",
        "isopact.evidence.ingest", "isopact.evidence.reduce", "isopact.invariants.evaluate",
        "isopact.settlement.evaluate", "isopact.claim.append", "isopact.kms.checkpoint.sign",
        "isopact.kms.receipt.sign", "isopact.receipt.verify",
    ),
    "reconciliation": ("isopact.invariants.evaluate", "isopact.resolver.reason", "isopact.resolution.validate", "isopact.compensation.precondition", "isopact.compensation.execute"),
    "toctou": ("isopact.invariants.evaluate", "isopact.resolution.validate", "isopact.compensation.precondition", "isopact.compensation.execute"),
    "outcome_unknown": ("isopact.invariants.evaluate", "isopact.resolution.validate", "isopact.compensation.precondition", "isopact.compensation.execute"),
}


def safe_trace(trace: dict) -> dict:
    return {"trace_id": trace.get("traceId"), "spans": [{
        "span_id": span.get("spanId"), "parent_span_id": span.get("parentSpanId"),
        "name": span.get("name"), "start_time": span.get("startTime"), "end_time": span.get("endTime"),
        "labels": {k: v for k, v in span.get("labels", {}).items() if k.startswith("isopact.") or k.startswith("gen_ai.")},
    } for span in trace.get("spans", [])]}


def trace_matches(trace: dict, pact_id: str) -> bool:
    return any(pact_id in str(value) for span in trace.get("spans", []) for value in span.get("labels", {}).values())


def retrieve(project: str, pacts: dict[str, str], polls: int, start_time: str, end_time: str) -> dict[str, list[dict]]:
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    session = AuthorizedSession(credentials)
    base = f"https://cloudtrace.googleapis.com/v1/projects/{project}/traces"
    results = {scenario: [] for scenario in pacts}
    seen: set[str] = set()
    for poll in range(polls):
        for scenario, pact_id in pacts.items():
            for name in SCENARIO_SPANS[scenario]:
                span_filter = f"+span:{name} +label:isopact.pact_id:{pact_id}"
                if name == "isopact.receipt.verify":
                    span_filter = f"+span:{name}"
                for attempt in range(5):
                    response = session.get(base, params={"filter": span_filter, "startTime": start_time, "endTime": end_time, "pageSize": 20}, timeout=30)
                    if response.status_code != 429:
                        break
                    time.sleep(5 * (attempt + 1))
                response.raise_for_status()
                for summary in response.json().get("traces", []):
                    trace_id = summary["traceId"]
                    cache_key = f"{scenario}:{trace_id}"
                    if cache_key in seen:
                        continue
                    seen.add(cache_key)
                    trace = session.get(f"{base}/{trace_id}", timeout=30).json()
                    if trace_matches(trace, pact_id) and all(item.get("trace_id") != trace_id for item in results[scenario]):
                        results[scenario].append(safe_trace(trace))
                time.sleep(0.75)
        if all(results.values()) or poll == polls - 1:
            break
        time.sleep(10)
    return results


def business_snapshot(db, pact_id: str) -> dict:
    ref = db.collection("pacts").document(pact_id)
    root = ref.get().to_dict() or {}
    collections = {}
    for name in ("claims", "evidence", "invariant_conflicts", "compensation_executions", "settlement_receipts", "graph_checkpoints"):
        collections[name] = [doc.to_dict() for doc in ref.collection(name).stream()]
    return {"root": root, "collections": collections}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--primary", required=True)
    parser.add_argument("--reconciliation", required=True)
    parser.add_argument("--toctou", required=True)
    parser.add_argument("--outcome-unknown", required=True)
    parser.add_argument("--polls", type=int, default=3)
    parser.add_argument("--start-time", default="2026-08-24T20:50:00Z")
    parser.add_argument("--end-time", default="2026-08-24T21:07:00Z")
    args = parser.parse_args()
    pacts = {"primary": args.primary, "reconciliation": args.reconciliation, "toctou": args.toctou, "outcome_unknown": args.outcome_unknown}
    traces = retrieve(args.project, pacts, args.polls, args.start_time, args.end_time)
    db = firestore.Client(project=args.project)
    OUT.mkdir(parents=True, exist_ok=True)
    overall = True
    for scenario, pact_id in pacts.items():
        present = sorted({span["name"] for trace in traces[scenario] for span in trace["spans"]})
        snapshot = business_snapshot(db, pact_id)
        result = "PASS_LIVE_RETRIEVED" if traces[scenario] else "BLOCKED_NO_LIVE_TRACE"
        overall &= bool(traces[scenario])
        bundle = {"scenario": scenario, "pact": pact_id, "source": "LIVE_CLOUD_TRACE_AND_FIRESTORE", "trace_ids": [t["trace_id"] for t in traces[scenario]], "live_spans": present, "traces": traces[scenario], "business_snapshot": snapshot, "completeness_result": result}
        filename = scenario.replace("_", "-") + "-causal-bundle.json"
        (OUT / filename).write_text(json.dumps(bundle, indent=2, default=str), encoding="utf-8")
    summary = {"source": "LIVE_CLOUD_TRACE", "pacts": pacts, "retrieved_trace_counts": {key: len(value) for key, value in traces.items()}, "live_span_union": sorted({span["name"] for scenario in traces.values() for trace in scenario for span in trace["spans"]}), "required_span_names": list(SPAN_NAMES), "missing_required_span_names": sorted(set(SPAN_NAMES) - {span["name"] for scenario in traces.values() for trace in scenario for span in trace["spans"]}), "result": "PASS" if overall else "BLOCKED"}
    (OUT / "stage10c-live-retrieval.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
