from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import google.auth
from google.auth import impersonated_credentials
from google.cloud import firestore, kms_v1

from isopact.security.provenance import build_settlement_receipt, verify_integrity_bundle
from isopact.security.signing import KmsDocumentSigner


OUT = ROOT / "artifacts" / "security"
SCOPE = "https://www.googleapis.com/auth/cloud-platform"


def write(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="isopact-agentic-20260823")
    parser.add_argument("--pact-id", required=True)
    parser.add_argument("--signer-service-account", required=True)
    parser.add_argument("--key-version", required=True)
    args = parser.parse_args()
    db = firestore.Client(project=args.project)
    pact_ref = db.collection("pacts").document(args.pact_id)
    pact = pact_ref.get().to_dict()
    claims = json.loads((OUT / "stateclaims.json").read_text())
    checkpoint = json.loads((OUT / "live-kms-checkpoint.json").read_text())
    economic = json.loads((OUT / "economic-derivation.json").read_text())
    keys = json.loads((OUT / "public-keys.json").read_text())
    evidence = [d.to_dict() for d in pact_ref.collection("evidence").stream()]
    roles = {}
    for claim in claims:
        identity = claim.get("agent_identity")
        if not identity:
            continue
        role = (claim.get("normalized_payload") or {}).get("role")
        roles.setdefault(identity, set())
        if role:
            roles[identity].add(role)
    participants = [
        {
            "participant_id": f"participant_{identity}",
            "kind": "AGENT",
            "display_name": identity,
            "authenticated_principal": identity,
            "roles": sorted(role_set),
            "derived_from_claim_ids": sorted(c["claim_id"] for c in claims if c.get("agent_identity") == identity),
        }
        for identity, role_set in sorted(roles.items())
    ]
    remote_case = json.loads((ROOT / "artifacts" / "agents" / "stage8b-end-to-end.json").read_text())
    resolver = remote_case["resolver"]
    participants.append({
        "participant_id": "participant_isopact-resolver-v1",
        "kind": "AGENT",
        "display_name": "isopact-resolver-v1",
        "authenticated_principal": "isopact-resolver-v1",
        "roles": ["RESOLVER"],
        "derived_from_claim_ids": [],
        "derived_from_remote_invocation_ids": resolver["invocation_ids"],
        "consequential_execution_performed": resolver["gateway"]["execution_performed"],
    })
    participants.sort(key=lambda item: item["participant_id"])
    source, _ = google.auth.default(scopes=[SCOPE])
    delegated = impersonated_credentials.Credentials(
        source_credentials=source, target_principal=args.signer_service_account,
        target_scopes=[SCOPE], lifetime=900,
    )
    signer = KmsDocumentSigner(args.key_version, kms_v1.KeyManagementServiceClient(credentials=delegated))
    receipt_id = f"receipt_{args.pact_id}_{checkpoint['through_sequence']:08d}_all-participants"
    receipt = build_settlement_receipt(
        pact=pact, checkpoint=checkpoint, economic_position=economic["assertions"] | {
            key: value for key, value in json.loads((OUT / "signed-settlement-summary.json").read_text())["economic_position"].items()
        },
        authoritative_evidence_ids=[x["evidence_id"] for x in evidence if x.get("evidence_rank") == 1],
        participants=participants,
        reconciliation_actions=[d.to_dict() for d in pact_ref.collection("reconciliation_actions").stream()],
        approval_references=[], exceptions=[], settlement_timestamp=pact["updated_at"],
        signer=signer, receipt_id=receipt_id,
    )
    verification = verify_integrity_bundle(receipt=receipt, checkpoint=checkpoint, claims=claims, public_keys=keys)
    if not verification["overall_integrity_valid"] or len(participants) != 4:
        raise RuntimeError(f"participant-bound receipt failed: {verification}, participants={participants}")
    pact_ref.collection("settlement_receipts").document(receipt_id).create(receipt)
    tampered = copy.deepcopy(receipt)
    tampered["economic_position"]["settled_total_compensation"] += 1
    write("final-settlement-receipt.json", receipt)
    write("tampered-receipt.json", tampered)
    write("full-verification.json", verification)
    summary = json.loads((OUT / "signed-settlement-summary.json").read_text())
    summary["receipt_id"] = receipt_id
    summary["participants"] = participants
    summary["verification"] = verification
    write("signed-settlement-summary.json", summary)
    print(json.dumps({"receipt_id": receipt_id, "participants": participants, "verification": verification}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
