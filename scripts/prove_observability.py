from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import google.auth
from google.auth.transport.requests import AuthorizedSession

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "observability"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="isopact-agentic-20260823")
    parser.add_argument("--pact-id", required=True)
    parser.add_argument("--polls", type=int, default=8)
    args = parser.parse_args()
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    session = AuthorizedSession(credentials)
    base = f"https://cloudtrace.googleapis.com/v1/projects/{args.project}/traces"
    found: list[dict] = []
    for _ in range(args.polls):
        response = session.get(base, params={"filter": "+span:isopact.gateway.request", "pageSize": 50}, timeout=30)
        response.raise_for_status()
        for summary in response.json().get("traces", []):
            trace = session.get(f"{base}/{summary['traceId']}", timeout=30).json()
            labels = [span.get("labels", {}) for span in trace.get("spans", [])]
            if any(item.get("isopact.pact_id") == args.pact_id for item in labels):
                found.append(trace)
        if found:
            break
        time.sleep(10)
    safe = [{
        "projectId": trace.get("projectId"), "traceId": trace.get("traceId"),
        "spans": [{
            "spanId": span.get("spanId"), "parentSpanId": span.get("parentSpanId"),
            "name": span.get("name"), "startTime": span.get("startTime"),
            "endTime": span.get("endTime"),
            "labels": {key: value for key, value in span.get("labels", {}).items()
                       if key.startswith("isopact.") or key in {"service.name", "cloud.region", "telemetry.sdk.version"}},
        } for span in trace.get("spans", [])],
    } for trace in found]
    names = {s["name"] for t in safe for s in t["spans"]}
    def artifact(name: str) -> dict:
        path = OUT / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    retrieval = artifact("stage10c-live-retrieval.json")
    logs = artifact("log-correlation.json")
    metrics = artifact("metrics-proof.json")
    privacy = artifact("privacy-audit.json")
    canary = artifact("privacy-canary.json")
    dashboard = artifact("dashboard.json")
    propagation = artifact("trace-propagation.json")
    async_link = artifact("async-span-link.json")
    bundles = [
        artifact(f"{scenario}-causal-bundle.json")
        for scenario in ("primary", "reconciliation", "toctou", "outcome-unknown")
    ]
    checks = {
        "primary_gateway_trace_retrieved_now": bool(found),
        "required_spans_live": (
            retrieval.get("source", "").startswith("LIVE_")
            and not retrieval.get("missing_required_span_names", ["missing"])
        ),
        "four_live_scenario_bundles": all(
            item.get("source", "").startswith("LIVE_") and item.get("trace_ids")
            for item in bundles
        ),
        "trace_correlated_logs_live": logs.get("source") == "LIVE_CLOUD_LOGGING" and logs.get("result") == "PASS",
        "required_metrics_live": metrics.get("source") == "LIVE_CLOUD_MONITORING_METRIC_DESCRIPTORS" and metrics.get("result") == "PASS",
        "privacy_canary_clean": canary.get("result") == "PASS" and canary.get("trace_matches") == 0 and canary.get("logging_matches") == 0,
        "privacy_audit_clean": privacy.get("result") == "PASS",
        "dashboard_live_and_complete": dashboard.get("source") == "LIVE_CLOUD_MONITORING_DASHBOARD" and dashboard.get("result") == "PASS" and bool(dashboard.get("deployedResource")),
        "w3c_sync_propagation_live": propagation.get("source") == "LIVE_CLOUD_TRACE" and propagation.get("result") == "PASS",
        "async_span_link_live": str(async_link.get("source", "")).startswith("LIVE_CLOUD_TRACE") and async_link.get("result") == "PASS",
    }
    proof = {
        "pact_id": args.pact_id,
        "retrieved_trace_count": len(safe),
        "present": sorted(names),
        "checks": checks,
        "blocking_checks": [name for name, passed in checks.items() if not passed],
        "result": "PASS" if all(checks.values()) else "BLOCKED",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "primary-protected-trace.json").write_text(json.dumps(safe, indent=2), encoding="utf-8")
    (OUT / "trace-completeness.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print(json.dumps(proof, indent=2))
    return 0 if proof["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
