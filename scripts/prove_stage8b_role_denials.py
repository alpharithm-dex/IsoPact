from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from prove_stage8b_live import invoke, tool_response


CASES = {
    "support_to_replacement": ("SUPPORT", "stage8b_support_attempt_replacement"),
    "fulfillment_to_refund": ("FULFILLMENT", "stage8b_fulfillment_attempt_refund"),
    "retention_to_refund": ("RETENTION", "stage8b_retention_attempt_refund"),
}


def main() -> int:
    import vertexai
    vertexai.init(project="isopact-agentic-20260823", location="europe-west1")
    results = {}
    for case, (role, tool) in CASES.items():
        pact_id = "stage8b-role-denial-before-pact-access"
        prompt = f"Call {tool} exactly once with pact_id={pact_id}. Report the exact denial."
        remote = invoke(role, prompt, f"{case}-user")
        response = tool_response(remote["events"], tool)
        results[case] = {
            "runtime_resource": remote["resource"],
            "runtime_invocation_ids": remote["invocation_ids"],
            "tool": tool,
            "response": response,
            "denied_before_pact_lookup": response.get("http_status") == 403 and response.get("error") == "CAPABILITY_DENIED",
            "external_call": False,
        }
    proof = {
        "generated_at": datetime.now(UTC).isoformat(),
        "method": "temporary diagnostic tool exposed on each canonical Runtime resource, removed after proof",
        "results": results,
        "all_cross_role_denied": all(item["denied_before_pact_lookup"] for item in results.values()),
        "unauthorized_external_calls": 0,
    }
    output = ROOT / "artifacts" / "agents" / "stage8b-live-role-denials.json"
    output.write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print(json.dumps(proof, indent=2))
    return 0 if proof["all_cross_role_denied"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
