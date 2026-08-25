from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

PROJECT = "isopact-agentic-20260823"
REGION = "europe-west1"
SUPPORT = "projects/442539309409/locations/europe-west1/reasoningEngines/1997126532413259776"


def sanitize(value):
    if isinstance(value, dict):
        return {key: sanitize(item) for key, item in value.items() if key != "thought_signature"}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value


def main() -> int:
    import vertexai
    from google.cloud import firestore
    from vertexai import agent_engines
    from isopact.evidence.firestore import FirestorePactGraphRepository
    from isopact.evidence.pipeline import utc_now
    from isopact.reservations.firestore import FirestoreReservationRepository
    from prove_agent_fleet import active_pact

    namespace = "stage8b-smoke-" + datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    active = active_pact(namespace)
    client = firestore.Client(project=PROJECT)
    FirestoreReservationRepository(PROJECT, client=client).activate(active.pact.pact_id, active.to_document())
    FirestorePactGraphRepository(PROJECT, client=client).activate_graph(active, utc_now())
    prompt = (
        f"Call request_refund_through_isopact exactly once for pact_id={active.pact.pact_id}, "
        "order_id=ORD-8472, session_id=stage8b-smoke-support, "
        "trace_id=trace-stage8b-smoke-support, request_id=req-stage8b-smoke-support, "
        "amount_minor_units=20000. Report the exact gateway result."
    )
    vertexai.init(project=PROJECT, location=REGION)
    remote = agent_engines.get(SUPPORT)
    events = [sanitize(event) for event in remote.stream_query(message=prompt, user_id="stage8b-smoke-user")]
    proof = {
        "generated_at": datetime.now(UTC).isoformat(),
        "pact_id": active.pact.pact_id,
        "resource": SUPPORT,
        "events": events,
        "external_objects": [item.to_dict() for item in client.collection("pacts").document(active.pact.pact_id).collection("external_objects").stream()],
    }
    output = ROOT / "artifacts" / "agents" / "stage8b-authenticated-smoke.json"
    output.write_text(json.dumps(proof, indent=2, default=str), encoding="utf-8")
    print(json.dumps(proof, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
