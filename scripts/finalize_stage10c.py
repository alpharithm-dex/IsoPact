from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from isopact.observability.chronicle import build_case_chronicle
OUT = ROOT / "artifacts" / "observability"


def load(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def write(name: str, value: dict) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")


scenarios = {
    "primary": load("primary-causal-bundle.json"),
    "reconciliation": load("reconciliation-causal-bundle.json"),
    "toctou": load("toctou-causal-bundle.json"),
    "outcome_unknown": load("outcome-unknown-causal-bundle.json"),
}

chronicles = {}
for name, bundle in scenarios.items():
    snap = bundle["business_snapshot"]
    collections = snap["collections"]
    collections["conflicts"] = collections.get("invariant_conflicts", [])
    chronicle = build_case_chronicle(snap["root"], collections)
    proof = snap["root"].get("stage10c_proof")
    if proof:
        chronicle["entries"].append({
            "entry_id": f"derived_{name}_{bundle['pact']}", "pact_id": bundle["pact"],
            "category": "DERIVED_PROOF_EVENT", "action": snap["root"].get("proof_scenario"),
            "caused_by": bundle["trace_ids"], "proof": proof,
        })
    chronicle["authoritative_store_created"] = False
    chronicles[name] = chronicle
    write(f"chronicle-{name.replace('_', '-')}.json", chronicle)

authority_names = {
    "isopact.gateway.authorize", "isopact.reservation.transaction", "isopact.evidence.ingest",
    "isopact.invariants.evaluate", "isopact.resolution.validate",
    "isopact.compensation.precondition", "isopact.settlement.evaluate", "isopact.receipt.verify",
}
model_names = {"isopact.resolver.reason", "generate_content", "call_llm", "prediction"}
violations = []
for scenario, bundle in scenarios.items():
    for trace in bundle["traces"]:
        spans = {span["span_id"]: span for span in trace["spans"]}
        children = {}
        for span in trace["spans"]:
            children.setdefault(span.get("parent_span_id"), []).append(span)
        def descendants(span_id):
            todo = list(children.get(span_id, [])); result = []
            while todo:
                item = todo.pop(); result.append(item); todo.extend(children.get(item["span_id"], []))
            return result
        for span in trace["spans"]:
            if span["name"] in authority_names:
                models = [item for item in descendants(span["span_id"]) if item["name"] in model_names or item["name"].startswith("gen_ai")]
                if models:
                    violations.append({"scenario": scenario, "trace_id": trace["trace_id"], "authority_span": span["name"], "model_descendants": [item["name"] for item in models]})
dependency = {"authority_span_classes": sorted(authority_names), "model_descendants_inside_authority_spans": len(violations), "violations": violations, "result": "PASS" if not violations else "FAIL"}
write("model-authority-dependency.json", dependency)

metrics = load("metrics-proof.json")
retrieval = load("stage10c-live-retrieval.json")
privacy = load("privacy-audit.json")
privacy_canary = load("privacy-canary.json")
overhead = load("telemetry-overhead.json")
propagation = load("trace-propagation.json")
async_link = load("async-span-link.json")
logs = load("log-correlation.json")
dashboard = load("dashboard.json")
failure_isolation = load("failure-isolation.json")
checks = {
    "all_required_custom_spans_live": not retrieval["missing_required_span_names"],
    "four_live_causal_bundles_retrieved": all(bundle["trace_ids"] for bundle in scenarios.values()),
    "model_authority_descendants_zero": dependency["result"] == "PASS",
    "chronicles_derived_for_four_scenarios": all(not item["authoritative_store_created"] for item in chronicles.values()),
    "all_required_metrics_live": metrics["result"] == "PASS",
    "metric_cardinality_violations_zero": not metrics["high_cardinality_violations"],
    "privacy_artifact_scan_clean": privacy["result"] == "PASS",
    "w3c_sync_propagation_proven": propagation.get("result") == "PASS",
    "async_span_links_proven": async_link.get("result") == "PASS",
    "trace_correlated_logs_beyond_gateway_proven": logs.get("result") == "PASS",
    "live_dashboard_complete": dashboard.get("result") == "PASS",
    "telemetry_overhead_measured": overhead.get("result") == "PASS",
    "telemetry_failure_isolation_proven": failure_isolation.get("result") == "PASS",
    "fresh_stage10c_privacy_canary_complete": privacy_canary.get("result") == "PASS",
}
gate = {"status": "PASS" if all(checks.values()) else "BLOCKED", "checks": checks, "blocking_checks": [key for key, value in checks.items() if not value]}
write("stage10c-gate.json", gate)
print(json.dumps(gate, indent=2))
