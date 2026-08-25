from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import vertexai

from prove_stage8b_live import invoke, response_summary


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "observability" / "sync-runtime-invocation.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--region", default="europe-west1")
    parser.add_argument("--pact", required=True)
    args = parser.parse_args()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    vertexai.init(project=args.project, location=args.region)
    prompt = (
        "Call request_refund_through_isopact exactly once for "
        f"pact_id={args.pact}, order_id=ORD-8472, "
        f"session_id=stage10c-sync-{stamp}, trace_id=logical-stage10c-sync-{stamp}, "
        f"request_id=req-stage10c-sync-{stamp}, amount_minor_units=20000. "
        "Report the exact result."
    )
    raw = invoke("SUPPORT", prompt, f"stage10c-sync-user-{stamp}")
    summary = response_summary(raw, "request_refund_through_isopact")
    result = {
        "source": "LIVE_AGENT_RUNTIME_AND_GATEWAY",
        "generated_at": datetime.now(UTC).isoformat(),
        "pact": args.pact,
        "invocation_ids": summary["invocation_ids"],
        "gateway": summary["gateway"],
        "errors": summary["errors"],
        "result": (
            "PASS"
            if summary["gateway"].get("gateway_decision") == "BLOCK"
            and summary["gateway"].get("reason_code") == "DUPLICATE_OPERATION"
            and not summary["gateway"].get("external_call_executed")
            else "FAIL"
        ),
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
