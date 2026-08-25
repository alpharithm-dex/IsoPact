from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import google.auth
from google.auth import impersonated_credentials
from google.cloud import firestore, secretmanager

from isopact.evidence.canonical import GENESIS_CLAIM_HASH
from isopact.evidence.firestore import FirestorePactGraphRepository
from isopact.evidence.pipeline import EvidencePipeline
from isopact.security.secrets import SecretManagerValue
from isopact.security.webhooks import (
    AuthenticatedEvidenceIngress,
    WebhookAuthenticationError,
    stripe_style_signature,
)


SCOPE = "https://www.googleapis.com/auth/cloud-platform"


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def counts(ref) -> dict[str, int]:
    return {name: len(list(ref.collection(name).stream())) for name in ("evidence", "claims", "settlement_proofs")}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="isopact-agentic-20260823")
    parser.add_argument("--evidence-service-account", required=True)
    parser.add_argument("--secret-version", required=True)
    args = parser.parse_args()

    pact_id = f"pact_stage9-auth-evidence-{datetime.now(timezone.utc):%Y%m%d%H%M%S}_{uuid.uuid4().hex[:12]}"
    source, _ = google.auth.default(scopes=[SCOPE])
    admin_db = firestore.Client(project=args.project)
    ref = admin_db.collection("pacts").document(pact_id)
    created = iso_now()
    operation = uuid.uuid4().hex
    ref.create({
        "pact_id": pact_id,
        "status": "ACTIVE",
        "graph_state": "PENDING",
        "selected_resolution": "successful_refund",
        "completion_evidence": {"successful_refund": ["stripe.refund.succeeded"]},
        "evidence_max_rank": {"successful_refund": 1},
        "resolved_operations": {},
        "graph_revision": 0,
        "settlement_generation": 1,
        "settlement_transition_count": 0,
        "settlement_evidence_ids": [],
        "claim_sequence": 0,
        "claim_count": 0,
        "terminal_claim_hash": GENESIS_CLAIM_HASH,
        "policy_id": "commerce_missing_order_v1",
        "policy_version": "1",
        "transaction": {"currency": "USD", "minor_units": 20000},
        "order_id": "ORD-STAGE9-AUTH",
        "created_at": created,
        "updated_at": created,
    })

    delegated = impersonated_credentials.Credentials(
        source_credentials=source,
        target_principal=args.evidence_service_account,
        target_scopes=[SCOPE],
        lifetime=900,
    )
    db = firestore.Client(project=args.project, credentials=delegated)
    secrets = secretmanager.SecretManagerServiceClient(credentials=delegated)
    provider = SecretManagerValue(args.secret_version, secrets)
    pipeline = EvidencePipeline(FirestorePactGraphRepository(args.project, client=db))
    ingress = AuthenticatedEvidenceIngress(pipeline, provider.access)
    raw = json.dumps({
        "event_type": "stripe.refund.succeeded",
        "source_system": "stripe",
        "pact_id": pact_id,
        "source_event_id": f"evt-stage9-{uuid.uuid4().hex}",
        "subject": "ORD-STAGE9-AUTH",
        "external_object_id": f"REF-{uuid.uuid4().hex[:12]}",
        "operation_identity": operation,
        "operation_attempt": 1,
        "occurred_at": iso_now(),
        "trace_id": f"trace-{uuid.uuid4().hex}",
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    epoch = int(time.time())
    forged_attempts = []
    for label, header in (
        ("missing", ""),
        ("invalid", f"t={epoch},v1={'0' * 64}"),
        ("stale", stripe_style_signature(provider.access(), raw, epoch - 301)),
    ):
        before = counts(ref)
        try:
            ingress.ingest(raw, header, now_epoch=epoch)
            outcome = "UNEXPECTED_ACCEPT"
        except WebhookAuthenticationError as exc:
            outcome = str(exc)
        after = counts(ref)
        forged_attempts.append({"case": label, "outcome": outcome, "before": before, "after": after, "rank1_created": after["evidence"] > before["evidence"]})

    valid_header = stripe_style_signature(provider.access(), raw, epoch)
    result = ingress.ingest(raw, valid_header, now_epoch=epoch)
    final = ref.get().to_dict()
    proof = {
        "status": "PASS" if all(not x["rank1_created"] for x in forged_attempts) and result.pact_state.value == "SETTLED" else "FAIL",
        "project": args.project,
        "pact_id": pact_id,
        "secret_resource": args.secret_version,
        "secret_value_exposed": False,
        "ingestion_principal": args.evidence_service_account,
        "forged_attempts": forged_attempts,
        "authenticated_attempt": {
            "accepted": True,
            "evidence_id": result.evidence_id,
            "evidence_rank": 1,
            "pact_state": result.pact_state.value,
            "settlement_transition_created": result.settlement_transition_created,
        },
        "final_claim_count": final["claim_count"],
        "terminal_claim_hash": final["terminal_claim_hash"],
    }
    output = ROOT / "artifacts" / "security" / "forged-evidence-rejection.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(proof, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
