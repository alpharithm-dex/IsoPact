from __future__ import annotations

import argparse
import json
from pathlib import Path

import google.auth
from google.auth.transport.requests import AuthorizedSession


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "observability" / "trace-propagation.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--pact", required=True)
    parser.add_argument("--invocation-id", required=True)
    parser.add_argument("--start-time", required=True)
    parser.add_argument("--end-time", required=True)
    args = parser.parse_args()
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    session = AuthorizedSession(credentials)
    base = f"https://cloudtrace.googleapis.com/v1/projects/{args.project}/traces"
    def summaries(filter_value: str) -> list[dict]:
        response = session.get(
            base,
            params={
                "filter": filter_value,
                "startTime": args.start_time,
                "endTime": args.end_time,
                "pageSize": 1000,
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("traces", [])

    gateway_summaries = summaries("+span:isopact.gateway.request")
    runtime_summaries = summaries(
        f"+label:gcp.vertex.agent.invocation_id:{args.invocation_id}"
    )
    candidate_ids = {
        item["traceId"] for item in (*gateway_summaries, *runtime_summaries)
    }
    matches = []
    pact_gateway_trace_ids = []
    invocation_trace_ids = []
    gateway_trace_details = []
    for trace_id in sorted(candidate_ids):
        trace = session.get(f"{base}/{trace_id}", timeout=30).json()
        spans = trace.get("spans", [])
        invocation_spans = [
            span for span in spans
            if span.get("labels", {}).get("gcp.vertex.agent.invocation_id") == args.invocation_id
        ]
        gateway_spans = [span for span in spans if span.get("name") == "isopact.gateway.request"]
        gateway_spans = [
            span for span in gateway_spans
            if span.get("labels", {}).get("isopact.pact_id") == args.pact
        ]
        if gateway_spans:
            pact_gateway_trace_ids.append(trace_id)
            gateway_trace_details.append({
                "trace_id": trace_id,
                "spans": [
                    {
                        "name": span.get("name"),
                        "span_id": span.get("spanId"),
                        "parent_span_id": span.get("parentSpanId"),
                        "invocation_id": span.get("labels", {}).get(
                            "gcp.vertex.agent.invocation_id"
                        ),
                    }
                    for span in spans
                ],
            })
        if invocation_spans:
            invocation_trace_ids.append(trace_id)
        platform_ids = {span.get("spanId") for span in invocation_spans}
        spans_by_id = {span.get("spanId"): span for span in spans}

        def reaches_runtime(span: dict) -> bool:
            parent_id = span.get("parentSpanId")
            visited = set()
            while parent_id and parent_id not in visited:
                if parent_id in platform_ids:
                    return True
                visited.add(parent_id)
                parent_id = spans_by_id.get(parent_id, {}).get("parentSpanId")
            return False

        parent_matches = [span for span in gateway_spans if reaches_runtime(span)]
        if invocation_spans and gateway_spans:
            matches.append({
                "trace_id": trace.get("traceId"),
                "invocation_span_ids": [span.get("spanId") for span in invocation_spans],
                "gateway_span_ids": [span.get("spanId") for span in gateway_spans],
                "gateway_parent_span_ids": [span.get("parentSpanId") for span in gateway_spans],
                "runtime_ancestor_matches": [span.get("spanId") for span in parent_matches],
                "span_names": sorted({span.get("name") for span in spans}),
            })
    result = {
        "source": "LIVE_CLOUD_TRACE",
        "pact": args.pact,
        "runtime_invocation_id": args.invocation_id,
        "pact_gateway_trace_ids": sorted(set(pact_gateway_trace_ids)),
        "runtime_invocation_trace_ids": sorted(set(invocation_trace_ids)),
        "gateway_trace_details": gateway_trace_details,
        "trace_id_intersection": sorted(
            set(pact_gateway_trace_ids) & set(invocation_trace_ids)
        ),
        "matches": matches,
        "same_trace_proven": bool(matches),
        "runtime_ancestor_proven": any(item["runtime_ancestor_matches"] for item in matches),
    }
    result["result"] = (
        "PASS" if result["same_trace_proven"] and result["runtime_ancestor_proven"]
        else "BLOCKED"
    )
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
