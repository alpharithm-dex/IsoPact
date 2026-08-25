from __future__ import annotations

import argparse
import json
from pathlib import Path

import google.auth
from google.auth.transport.requests import AuthorizedSession


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "observability" / "log-correlation.json"
MESSAGES = {
    "evidence": "evidence ingestion decision",
    "invariants": "invariant evaluation failed",
    "settlement": "settlement lifecycle transition",
    "compensation": "compensation precondition failed",
    "receipt": "settlement receipt signed",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--execution", required=True)
    parser.add_argument("--gateway-trace", required=True)
    args = parser.parse_args()
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    session = AuthorizedSession(credentials)

    def entries(filter_value: str) -> list[dict]:
        response = session.post(
            "https://logging.googleapis.com/v2/entries:list",
            json={
                "resourceNames": [f"projects/{args.project}"],
                "filter": filter_value,
                "orderBy": "timestamp desc",
                "pageSize": 200,
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("entries", [])

    job_entries = entries(
        f'labels."run.googleapis.com/execution_name"="{args.execution}"'
    )
    gateway_entries = entries(
        'resource.type="cloud_run_revision" '
        'AND resource.labels.service_name="isopact-outcome-gateway" '
        'AND jsonPayload.message="gateway action decision" '
        f'AND trace="projects/{args.project}/traces/{args.gateway_trace}"'
    )

    def proof(message: str, source: list[dict]) -> dict:
        matched = [
            entry for entry in source
            if entry.get("jsonPayload", {}).get("message") == message
        ]
        correlated = [entry for entry in matched if entry.get("trace") and entry.get("spanId")]
        return {
            "message": message,
            "retrieved": len(matched),
            "trace_correlated": len(correlated),
            "traces": sorted({entry["trace"] for entry in correlated}),
            "span_ids": sorted({entry["spanId"] for entry in correlated}),
            "result": "PASS" if correlated else "BLOCKED",
        }

    categories = {
        "Gateway": proof("gateway action decision", gateway_entries),
        **{name: proof(message, job_entries) for name, message in MESSAGES.items()},
    }
    result = {
        "source": "LIVE_CLOUD_LOGGING",
        "execution": args.execution,
        "gateway_trace": args.gateway_trace,
        "categories": categories,
        "result": (
            "PASS"
            if all(item["result"] == "PASS" for item in categories.values())
            else "BLOCKED"
        ),
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
