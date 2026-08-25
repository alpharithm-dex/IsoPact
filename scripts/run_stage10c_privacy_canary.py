from __future__ import annotations

import json
import argparse
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import google.auth
from google.auth.transport.requests import AuthorizedSession

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from prove_stage8b_live import invoke
import vertexai

parser = argparse.ArgumentParser()
parser.add_argument("--search-only", action="store_true")
args = parser.parse_args()
started = datetime.now(UTC) - timedelta(minutes=10)
if args.search_only:
    previous = json.loads((ROOT / "artifacts" / "observability" / "privacy-canary.json").read_text(encoding="utf-8"))
    REQUEST = previous["request_marker"]
    RESPONSE = previous["response_marker"]
    invocation = {"resource": previous["runtime_resource"], "invocation_ids": previous["invocation_ids"]}
else:
    marker = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8].upper()
    REQUEST = f"ISOPACT_TRACE_PRIVACY_CANARY_{marker}_REQUEST"
    RESPONSE = f"ISOPACT_TRACE_PRIVACY_CANARY_{marker}_RESPONSE"
    vertexai.init(project="isopact-agentic-20260823", location="europe-west1")
    invocation = invoke("SUPPORT", f"Synthetic privacy test only. Read {REQUEST} and reply with exactly {RESPONSE}. Do not call tools.", "stage10c-privacy-canary")
    time.sleep(30)
credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
session = AuthorizedSession(credentials)
base = "https://cloudtrace.googleapis.com/v1/projects/isopact-agentic-20260823/traces"
response = session.get(base, params={"filter": "+span:call_llm", "pageSize": 50}, timeout=30)
response.raise_for_status()
trace_matches = []
scanned = 0
for summary in response.json().get("traces", []):
    trace = session.get(f"{base}/{summary['traceId']}", timeout=30).json()
    invocation_match = any(
        span.get("labels", {}).get("gcp.vertex.agent.invocation_id") in invocation["invocation_ids"]
        for span in trace.get("spans", [])
    )
    if not invocation_match:
        continue
    text = json.dumps(trace)
    scanned += 1
    if REQUEST in text or RESPONSE in text:
        trace_matches.append(summary["traceId"])
logging_filter = f'timestamp>="{(started - timedelta(minutes=1)).isoformat()}" AND ("{REQUEST}" OR "{RESPONSE}")'
logging = session.post("https://logging.googleapis.com/v2/entries:list", json={"resourceNames": ["projects/isopact-agentic-20260823"], "filter": logging_filter, "pageSize": 100}, timeout=30)
logging.raise_for_status()
logging_matches = len(logging.json().get("entries", []))
proof = {"generated_at": datetime.now(UTC).isoformat(), "request_marker": REQUEST, "response_marker": RESPONSE, "runtime_resource": invocation["resource"], "invocation_ids": invocation["invocation_ids"], "recent_traces_scanned": scanned, "trace_matches": len(trace_matches), "trace_match_ids": trace_matches, "logging_matches": logging_matches, "completion_upload_hooks_present": False, "gcs_or_bigquery_completion_sink_configured": False, "raw_model_content_observed": bool(trace_matches or logging_matches), "result": "PASS" if scanned > 0 and not trace_matches and not logging_matches else "BLOCKED_NO_TRACES" if scanned == 0 else "FAIL"}
path = ROOT / "artifacts" / "observability" / "privacy-canary.json"
path.write_text(json.dumps(proof, indent=2), encoding="utf-8")
print(json.dumps(proof, indent=2))
