from __future__ import annotations

import json
from pathlib import Path

import google.auth
from google.auth.transport.requests import AuthorizedSession

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "observability" / "metrics-proof.json"
PREFIX = "prometheus.googleapis.com/isopact."
REQUIRED = {
    "isopact.gateway.decisions", "isopact.duplicate_operations_blocked", "isopact.exclusive_conflicts_blocked",
    "isopact.evidence.received", "isopact.evidence.duplicates_deduped", "isopact.invariant.failures",
    "isopact.compensation.executions", "isopact.compensation.precondition_failures",
    "isopact.settlement.transitions", "isopact.receipts.signed", "isopact.gateway.authorization.duration",
    "isopact.reservation.duration", "isopact.evidence.processing.duration", "isopact.invariants.duration",
    "isopact.resolver.duration", "isopact.compensation.validation.duration", "isopact.claim.append.duration",
    "isopact.kms.sign.duration",
}
PROHIBITED = {"pact_id", "trace_id", "session_id", "customer_id", "order_id", "operation_identity", "receipt_id", "evidence_id"}

credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
session = AuthorizedSession(credentials)
url = "https://monitoring.googleapis.com/v3/projects/isopact-agentic-20260823/metricDescriptors"
response = session.get(url, params={"filter": f'metric.type = starts_with("{PREFIX}")', "pageSize": 1000}, timeout=30)
response.raise_for_status()
descriptors = response.json().get("metricDescriptors", [])
names = {"isopact." + item["type"].removeprefix(PREFIX).rsplit("/", 1)[0] for item in descriptors}
violations = sorted({label["key"] for item in descriptors for label in item.get("labels", [])} & PROHIBITED)
proof = {
    "source": "LIVE_CLOUD_MONITORING_METRIC_DESCRIPTORS",
    "retrieved": sorted(item["type"] for item in descriptors),
    "required": sorted(REQUIRED), "present_names": sorted(names),
    "missing": sorted(REQUIRED - names), "high_cardinality_violations": violations,
    "result": "PASS" if not (REQUIRED - names) and not violations else "BLOCKED_INCOMPLETE",
}
OUT.write_text(json.dumps(proof, indent=2), encoding="utf-8")
print(json.dumps(proof, indent=2))
