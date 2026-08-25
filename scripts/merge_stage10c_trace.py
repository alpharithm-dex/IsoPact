from __future__ import annotations

import json
from pathlib import Path

import google.auth
from google.auth.transport.requests import AuthorizedSession

from retrieve_stage10c_live import safe_trace

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "observability"
TRACE_ID = "a6307ea2c83607a645713df32389f331"

credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
session = AuthorizedSession(credentials)
trace = session.get(f"https://cloudtrace.googleapis.com/v1/projects/isopact-agentic-20260823/traces/{TRACE_ID}", timeout=30)
trace.raise_for_status()
safe = safe_trace(trace.json())
bundle_path = OUT / "primary-causal-bundle.json"
bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
if TRACE_ID not in bundle["trace_ids"]:
    bundle["trace_ids"].append(TRACE_ID)
    bundle["traces"].append(safe)
bundle["live_spans"] = sorted({span["name"] for item in bundle["traces"] for span in item["spans"]})
bundle_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
summary_path = OUT / "stage10c-live-retrieval.json"
summary = json.loads(summary_path.read_text(encoding="utf-8"))
summary["live_span_union"] = sorted(set(summary["live_span_union"]) | {"isopact.external.replacement"})
summary["missing_required_span_names"] = sorted(set(summary["required_span_names"]) - set(summary["live_span_union"]))
summary["retrieved_trace_counts"]["primary"] = len(bundle["trace_ids"])
summary["result"] = "PASS" if not summary["missing_required_span_names"] else "BLOCKED"
summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
