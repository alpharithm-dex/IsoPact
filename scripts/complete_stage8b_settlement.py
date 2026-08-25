from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from prove_stage8b_live import PROJECT, REGION, activate, external_objects, invoke, response_summary, write


def main() -> int:
    import vertexai
    from google.cloud import firestore
    from isopact.evidence.firestore import FirestorePactGraphRepository
    from isopact.evidence.pipeline import EvidencePipeline, utc_now

    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    client = firestore.Client(project=PROJECT)
    vertexai.init(project=PROJECT, location=REGION)
    active = activate(f"stage8b-settlement-{stamp}", client)
    raw = invoke("SUPPORT", (
        f"Call request_refund_through_isopact exactly once for pact_id={active.pact.pact_id}, order_id=ORD-8472, "
        "session_id=stage8b-settlement-support, trace_id=trace-stage8b-settlement-support, "
        "request_id=req-stage8b-settlement-support, amount_minor_units=20000. Report the exact result and do not call another tool."
    ), "stage8b-settlement-support-user")
    support = response_summary(raw, "request_refund_through_isopact")
    gateway = support["gateway"]
    graph = FirestorePactGraphRepository(PROJECT, client=client)
    pipeline = EvidencePipeline(graph)
    pipeline.record_text_claim(
        pact_id=active.pact.pact_id, source_kind="agent", source_actor="isopact-support-v1",
        text=raw["final_text"], occurred_at=utc_now(), trace_id="trace-stage8b-rank4",
    )
    before = graph.snapshot(active.pact.pact_id)
    result = pipeline.ingest_event({
        "pact_id": active.pact.pact_id,
        "source_system": "stripe",
        "source_event_id": f"evt-stage8b-settlement-{stamp}",
        "event_type": "stripe.refund.succeeded",
        "subject": "ORD-8472",
        "external_object_id": gateway["external_object"]["external_object_id"],
        "operation_identity": gateway["operation_identity"],
        "operation_attempt": 1,
        "occurred_at": utc_now(),
        "trace_id": "trace-stage8b-rank1",
    })
    after = graph.snapshot(active.pact.pact_id)
    proof = {
        "pact_id": active.pact.pact_id,
        "support": support,
        "rank4_statement": raw["final_text"],
        "state_after_rank4": before.state.value,
        "rank1_event": "stripe.refund.succeeded",
        "ingestion_result": asdict(result),
        "state_after_rank1": after.state.value,
        "before": asdict(before),
        "after": asdict(after),
        "external_objects": external_objects(client, active.pact.pact_id),
    }
    write("stage8b-agent-claim-vs-evidence.json", proof)
    write("stage8b-settled-support-end-to-end.json", proof)
    print(json.dumps({
        "pact_id": active.pact.pact_id,
        "state_after_rank4": before.state.value,
        "state_after_rank1": after.state.value,
        "external_execution_count": len(proof["external_objects"]),
    }, indent=2))
    return 0 if before.state.value != "SETTLED" and after.state.value == "SETTLED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
