from __future__ import annotations

import json
import os
import sys
import argparse
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from isopact.compiler.models import AuthoritativeCaseContext, AuthoritativeOrder, ValidationStatus
from isopact.compiler.pipeline import PactCompiler
from isopact.compiler.providers import GeminiPactCompilerProvider


REQUEST = (
    "My $200 order never arrived. I was told yesterday that it would be refunded "
    "or replaced. Can someone please resolve this?"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create sanitized live Vertex Gemini compiler evidence")
    parser.add_argument("--runs", type=int, default=1, choices=range(1, 6))
    args = parser.parse_args()
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
    if not project:
        print("BLOCKED: GOOGLE_CLOUD_PROJECT is not configured", file=sys.stderr)
        return 2
    context = AuthoritativeCaseContext(
        tenant="demo-retailer",
        domain="commerce",
        case_type="missing_order",
        ticket_id="JIRA-8472",
        orders=(
            AuthoritativeOrder(
                order_id="ORD-8472", customer_id="CUS-104",
                captured_minor_units=20_000, currency="USD",
            ),
        ),
    )
    compiler = PactCompiler(
        GeminiPactCompilerProvider(project=project, location=location, model=model)
    )
    results = [compiler.compile(REQUEST, context) for _ in range(args.runs)]
    successful_live = [
        result
        for result in results
        if result.model_contribution is not None
        and result.model_contribution.metadata.execution_mode == "LIVE"
        and result.deterministic_result.status is ValidationStatus.VALID
    ]
    if not successful_live:
        sanitized = [result.model_dump(mode="json") for result in results]
        print(json.dumps({"status": "BLOCKED", "results": sanitized}, sort_keys=True, indent=2), file=sys.stderr)
        return 1
    semantic_signatures = {
        json.dumps(
            {
                "outcome": result.model_contribution.candidate.candidate_outcome_type,
                "subjects": sorted(
                    (ref.subject_type, ref.value)
                    for ref in result.model_contribution.candidate.subject_references
                ),
                "resolution_concepts": sorted(result.model_contribution.candidate.candidate_resolution_paths),
                "validation": result.deterministic_result.status.value,
            },
            sort_keys=True,
        )
        for result in successful_live
    }
    artifact = {
        "schema_version": "stage3-live-proof-v1",
        "request_timestamp": datetime.now(UTC).isoformat(),
        "provider": "google-vertex-ai",
        "model": model,
        "project": project,
        "location": location,
        "live_calls": len(results),
        "successful_valid_calls": len(successful_live),
        "unique_semantic_signatures": len(semantic_signatures),
        "results": [result.model_dump(mode="json") for result in results],
    }
    output = ROOT / "artifacts" / "compiler" / "live-missing-order.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(artifact, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
