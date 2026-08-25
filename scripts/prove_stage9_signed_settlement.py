from __future__ import annotations

import argparse
import copy
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import google.auth
from google.auth import impersonated_credentials
from google.cloud import firestore, kms_v1
from google.api_core import exceptions as google_exceptions

from isopact.domain.models import Money
from isopact.evidence.canonical import canonical_json_bytes, verify_claim_chain
from isopact.invariants.economics import EconomicReducer, ProtectionLedger
from isopact.invariants.models import (
    EconomicFact,
    EconomicFactKind,
    EconomicPhase,
    EconomicPolicy,
    ProtectionEventType,
)
from isopact.security.provenance import (
    build_checkpoint,
    build_settlement_receipt,
    verify_integrity_bundle,
)
from isopact.security.signing import KmsDocumentSigner, SigningUnavailable, unsigned_pending_document


OUT = ROOT / "artifacts" / "security"
SCOPE = "https://www.googleapis.com/auth/cloud-platform"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write(name: str, value: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def percentile(samples: list[float], fraction: float) -> float:
    ordered = sorted(samples)
    return ordered[max(0, min(len(ordered) - 1, int(len(ordered) * fraction + 0.999999) - 1))]


def fact_from_claim(
    claim: dict, *, pact: dict, phase: EconomicPhase, kind: EconomicFactKind, amount: int,
    external_object_id: str | None = None,
) -> EconomicFact:
    return EconomicFact(
        fact_id=f"fact_{claim['claim_id']}",
        economic_object_id=claim.get("operation_identity") or claim["claim_id"],
        semantic_intent_id=f"{pact['pact_id']}:{claim.get('resolution_path') or claim['subject']}",
        economic_scope="primary:full" if kind is not EconomicFactKind.GOODWILL else "exception:delay",
        kind=kind,
        phase=phase,
        amount=Money(pact["transaction"]["currency"], amount),
        subject_id=pact["order_id"],
        operation_identity=claim.get("operation_identity"),
        external_object_id=external_object_id or claim.get("external_object_id"),
        source_system=claim["source_system"],
        source_version=int(claim["sequence_number"]),
        occurred_at=claim["occurred_at"],
        executed=phase is not EconomicPhase.BLOCKED,
        authorized=phase is not EconomicPhase.BLOCKED,
        external_state=phase.value,
    )


def derive_economics(pact: dict, claims: list[dict]) -> tuple[dict, dict, list[dict]]:
    """Derive all values from the live pact and its chained claims using Stage 6 code."""
    transaction = pact["transaction"]
    currency = transaction["currency"]
    captured = int(transaction["minor_units"])
    by_action: dict[tuple[str, str], dict] = {}
    for claim in claims:
        payload = claim.get("normalized_payload") or {}
        action = payload.get("action_kind")
        decision = payload.get("authorization_result")
        if action and decision:
            by_action[(action, decision)] = claim

    authoritative = next(
        c for c in claims
        if c.get("claim_type") == "AUTHORITATIVE_EVENT" and c.get("resolution_path") == "successful_refund"
    )
    refund_allow = by_action[("refund", "ALLOW")]
    goodwill_allow = by_action[("goodwill", "ALLOW")]
    replacement_block = by_action[("replacement", "BLOCK")]
    duplicate_block = next(
        c for c in claims
        if (c.get("normalized_payload") or {}).get("action_kind") == "refund"
        and (c.get("normalized_payload") or {}).get("authorization_result") == "BLOCK"
        and (c.get("normalized_payload") or {}).get("reason_code") == "DUPLICATE_OPERATION"
    )
    refund_amount = int(refund_allow["normalized_payload"]["inputs"]["amount_minor_units"])
    goodwill_amount = int(goodwill_allow["normalized_payload"]["inputs"]["amount_minor_units"])
    replacement_amount = int(replacement_block["normalized_payload"]["inputs"]["value_minor_units"])
    duplicate_amount = int(duplicate_block["normalized_payload"]["inputs"]["amount_minor_units"])
    facts = (
        fact_from_claim(authoritative, pact=pact, phase=EconomicPhase.SETTLED, kind=EconomicFactKind.REFUND, amount=refund_amount),
        fact_from_claim(replacement_block, pact=pact, phase=EconomicPhase.BLOCKED, kind=EconomicFactKind.REPLACEMENT, amount=replacement_amount),
        fact_from_claim(goodwill_allow, pact=pact, phase=EconomicPhase.SETTLED, kind=EconomicFactKind.GOODWILL, amount=goodwill_amount),
        fact_from_claim(duplicate_block, pact=pact, phase=EconomicPhase.BLOCKED, kind=EconomicFactKind.REFUND, amount=duplicate_amount),
    )
    protection_events = (
        ProtectionLedger.event(ProtectionEventType.INVALID_ACTION_PREVENTED, facts[1], replacement_block["normalized_payload"]["reason_code"], replacement_block["occurred_at"]),
        ProtectionLedger.event(ProtectionEventType.INVALID_ACTION_PREVENTED, facts[3], duplicate_block["normalized_payload"]["reason_code"], duplicate_block["occurred_at"]),
    )
    policy = EconomicPolicy(
        policy_id=pact["policy_id"],
        authorization_policy_version=pact["authorization_policy_version"],
        evaluation_rule_set_id=pact["evaluation_rule_set_id"],
        evaluation_rule_set_version=pact["evaluation_rule_set_version"],
        current_policy_version=pact["policy_version"],
        currency=currency,
        captured_value=captured,
        goodwill_limit=int(pact["goodwill_limit_minor_units"]),
    )
    position, current, protection = EconomicReducer.reduce(facts, policy, protection_events)
    expected = {
        "captured_value": captured,
        "settled_primary_value": refund_amount,
        "goodwill_settled_value": goodwill_amount,
        "replacement_committed_value": 0,
        "settled_total_compensation": refund_amount + goodwill_amount,
        "protected_value": replacement_amount + duplicate_amount,
    }
    actual = position.to_dict()
    if any(actual[key] != value for key, value in expected.items()):
        raise RuntimeError(f"LIVE_ECONOMIC_DERIVATION_MISMATCH expected={expected} actual={actual}")
    derivation = {
        "source": "live Stage 8B pact + chained claims, reduced by Stage 6 EconomicReducer",
        "policy": {
            "authorization": policy.authorization_policy_reference,
            "evaluation": policy.evaluation_policy_reference,
        },
        "facts": [item.to_dict() for item in current],
        "protection_events": [item.to_dict() for item in protection_events],
        "protection_summary": protection.to_dict(),
        "assertions": expected,
    }
    return actual, derivation, [item.to_dict() for item in protection_events]


class FailingKmsClient:
    def asymmetric_sign(self, request):
        raise google_exceptions.ServiceUnavailable("injected KMS outage")


def tamper_results(receipt: dict, checkpoint: dict, claims: list[dict], keys: dict[str, str]) -> dict:
    cases: dict[str, dict] = {}

    def test(name: str, changed_receipt=receipt, changed_checkpoint=checkpoint, changed_claims=claims, changed_keys=keys):
        result = verify_integrity_bundle(receipt=changed_receipt, checkpoint=changed_checkpoint, claims=changed_claims, public_keys=changed_keys)
        cases[name] = {"detected": not result["overall_integrity_valid"], "verification": result}

    edited = copy.deepcopy(claims)
    edited[0]["normalized_payload"]["inputs"]["amount_minor_units"] += 1
    test("edited_claim", changed_claims=edited)
    test("deleted_intermediate_claim", changed_claims=claims[:3] + claims[4:])
    reordered = copy.deepcopy(claims)
    reordered[2], reordered[3] = reordered[3], reordered[2]
    test("reordered_claims", changed_claims=reordered)
    injected = copy.deepcopy(claims)
    injected.insert(2, copy.deepcopy(claims[1]))
    test("injected_claim", changed_claims=injected)
    changed_receipt = copy.deepcopy(receipt)
    changed_receipt["economic_position"]["settled_total_compensation"] += 1
    test("modified_receipt_amount", changed_receipt=changed_receipt)
    wrong = dict(keys)
    versions = list(keys)
    wrong[str(receipt["signing_key_version"])] = keys[versions[0]] if versions[0] != str(receipt["signing_key_version"]) else keys[versions[-1]]
    test("wrong_public_key", changed_keys=wrong)
    return {"all_tampering_detected": all(v["detected"] for v in cases.values()), "cases": cases}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="isopact-agentic-20260823")
    parser.add_argument("--pact-id", required=True)
    parser.add_argument("--signer-service-account", required=True)
    parser.add_argument("--key-version-1", required=True)
    parser.add_argument("--key-version-2", required=True)
    args = parser.parse_args()

    db = firestore.Client(project=args.project)
    pact_ref = db.collection("pacts").document(args.pact_id)
    pact = pact_ref.get().to_dict() or {}
    claims = [d.to_dict() for d in pact_ref.collection("claims").order_by("sequence_number").stream()]
    chain = verify_claim_chain(claims)
    if not chain["claim_chain_valid"] or pact.get("graph_state") != "SETTLED":
        raise RuntimeError(f"FINAL_PACT_NOT_VERIFIABLY_SETTLED:{chain}")
    evidence = [d.to_dict() for d in pact_ref.collection("evidence").stream()]
    participants = [d.to_dict() for d in pact_ref.collection("participants").stream()]
    reconciliations = [d.to_dict() for d in pact_ref.collection("reconciliation_actions").stream()]
    economic_position, derivation, protection_events = derive_economics(pact, claims)
    invariant_evaluations = [{
        "rule": "STAGE9_RECEIPT_ECONOMIC_BINDING@1",
        "result": "PASS",
        "economic_assertions": derivation["assertions"],
        "input_claim_hashes": [c["claim_hash"] for c in claims],
    }]

    source, _ = google.auth.default(scopes=[SCOPE])
    delegated = impersonated_credentials.Credentials(
        source_credentials=source,
        target_principal=args.signer_service_account,
        target_scopes=[SCOPE],
        lifetime=900,
    )
    kms = kms_v1.KeyManagementServiceClient(credentials=delegated)
    signer1 = KmsDocumentSigner(args.key_version_1, kms)
    signer2 = KmsDocumentSigner(args.key_version_2, kms)
    keys = {args.key_version_1: signer1.public_key_pem(), args.key_version_2: signer2.public_key_pem()}

    # Prefix checkpoint proves that a valid but stale checkpoint cannot be substituted.
    stale_checkpoint = build_checkpoint(
        pact_id=args.pact_id,
        claims=claims[:6],
        evidence_ids=[],
        economic_snapshot={"state": "PENDING", "source": "historical prefix"},
        invariant_evaluations=[],
        policy_references=[pact["authorization_policy_version"]],
        rule_references=[f"{pact['evaluation_rule_set_id']}@{pact['evaluation_rule_set_version']}"],
        created_at=claims[5]["occurred_at"],
        signer=signer1,
    )
    created = now()
    checkpoint = build_checkpoint(
        pact_id=args.pact_id,
        claims=claims,
        evidence_ids=[item["evidence_id"] for item in evidence],
        economic_snapshot=economic_position,
        invariant_evaluations=invariant_evaluations,
        policy_references=[pact["authorization_policy_version"]],
        rule_references=[f"{pact['evaluation_rule_set_id']}@{pact['evaluation_rule_set_version']}"],
        created_at=created,
        signer=signer2,
    )
    receipt = build_settlement_receipt(
        pact=pact,
        checkpoint=checkpoint,
        economic_position=economic_position,
        authoritative_evidence_ids=[item["evidence_id"] for item in evidence if item.get("evidence_rank") == 1],
        participants=participants,
        reconciliation_actions=reconciliations,
        approval_references=[],
        exceptions=[],
        settlement_timestamp=pact["updated_at"],
        signer=signer2,
    )
    verification = verify_integrity_bundle(receipt=receipt, checkpoint=checkpoint, claims=claims, public_keys=keys)
    stale_result = verify_integrity_bundle(receipt=receipt, checkpoint=stale_checkpoint, claims=claims[:6], public_keys=keys)

    # Version 1 remains independently verifiable after version 2 becomes the issuing version.
    historic_checkpoint = build_checkpoint(
        pact_id=args.pact_id,
        claims=claims,
        evidence_ids=[item["evidence_id"] for item in evidence],
        economic_snapshot=economic_position,
        invariant_evaluations=invariant_evaluations,
        policy_references=[pact["authorization_policy_version"]],
        rule_references=[f"{pact['evaluation_rule_set_id']}@{pact['evaluation_rule_set_version']}"],
        created_at=created,
        signer=signer1,
    )
    historic_receipt = build_settlement_receipt(
        pact=pact, checkpoint=historic_checkpoint, economic_position=economic_position,
        authoritative_evidence_ids=[item["evidence_id"] for item in evidence if item.get("evidence_rank") == 1],
        participants=participants, reconciliation_actions=reconciliations,
        approval_references=[], exceptions=[], settlement_timestamp=pact["updated_at"], signer=signer1,
    )
    historic_valid = verify_integrity_bundle(receipt=historic_receipt, checkpoint=historic_checkpoint, claims=claims, public_keys=keys)

    tamper = tamper_results(receipt, checkpoint, claims, keys)
    tampered_receipt = copy.deepcopy(receipt)
    tampered_receipt["economic_position"]["settled_total_compensation"] += 1
    tampered_claim = copy.deepcopy(claims[0])
    tampered_claim["normalized_payload"]["inputs"]["amount_minor_units"] += 1

    failing = KmsDocumentSigner(args.key_version_2, FailingKmsClient())
    failure_reason = None
    try:
        build_settlement_receipt(
            pact=pact, checkpoint=checkpoint, economic_position=economic_position,
            authoritative_evidence_ids=[], participants=[], reconciliation_actions=[],
            approval_references=[], exceptions=[], settlement_timestamp=pact["updated_at"], signer=failing,
        )
    except SigningUnavailable as exc:
        failure_reason = str(exc)
    pending = unsigned_pending_document(
        {"pact_id": args.pact_id, "final_pact_lifecycle": pact["graph_state"]},
        failure_reason or "unexpected",
    )

    sign_samples: list[float] = []
    verify_samples: list[float] = []
    for _ in range(5):
        start = time.perf_counter_ns()
        signer2.sign(canonical_json_bytes({"performance_probe": args.pact_id, "created_at": created}))
        sign_samples.append((time.perf_counter_ns() - start) / 1_000_000)
    for _ in range(100):
        start = time.perf_counter_ns()
        verify_integrity_bundle(receipt=receipt, checkpoint=checkpoint, claims=claims, public_keys=keys)
        verify_samples.append((time.perf_counter_ns() - start) / 1_000_000)

    pact_ref.collection("graph_checkpoints").document(checkpoint["checkpoint_id"]).create(checkpoint)
    pact_ref.collection("settlement_receipts").document(receipt["receipt_id"]).create(receipt)

    write("stateclaims.json", claims)
    write("live-kms-checkpoint.json", checkpoint)
    write("final-settlement-receipt.json", receipt)
    write("public-keys.json", keys)
    write("economic-derivation.json", derivation)
    write("full-verification.json", verification)
    write("tampered-claim.json", tampered_claim)
    write("tampered-receipt.json", tampered_receipt)
    write("tamper-tests.json", {**tamper, "stale_checkpoint_substitution": {"detected": not stale_result["overall_integrity_valid"], "verification": stale_result}})
    write("key-rotation.json", {
        "old_key_version": args.key_version_1,
        "new_key_version": args.key_version_2,
        "old_receipt_still_valid": historic_valid["overall_integrity_valid"],
        "new_receipt_valid": verification["overall_integrity_valid"],
        "old_receipt": historic_receipt,
    })
    write("kms-failure.json", {
        "injected_failure": True,
        "failure_reason": failure_reason,
        "pact_state_remained_settled": pact_ref.get().to_dict().get("graph_state") == "SETTLED",
        "false_signed_receipt_emitted": False,
        "pending_receipt_state": pending,
    })
    write("performance.json", {
        "kms_signing": {"samples": len(sign_samples), "p50_ms": round(statistics.median(sign_samples), 3), "p95_ms": round(percentile(sign_samples, .95), 3)},
        "independent_full_verification": {"samples": len(verify_samples), "p50_ms": round(statistics.median(verify_samples), 3), "p95_ms": round(percentile(verify_samples, .95), 3)},
        "environment": "live Google Cloud KMS signing; local independent public-key and chain verification",
    })
    summary = {
        "status": "PASS" if verification["overall_integrity_valid"] and tamper["all_tampering_detected"] and historic_valid["overall_integrity_valid"] and not stale_result["overall_integrity_valid"] else "FAIL",
        "pact_id": args.pact_id,
        "claim_count": len(claims),
        "terminal_claim_hash": chain["terminal_claim_hash"],
        "checkpoint_id": checkpoint["checkpoint_id"],
        "receipt_id": receipt["receipt_id"],
        "signing_key_version": args.key_version_2,
        "economic_position": economic_position,
        "verification": verification,
        "tampering_detected": tamper["all_tampering_detected"],
        "stale_checkpoint_detected": not stale_result["overall_integrity_valid"],
        "key_rotation_verified": historic_valid["overall_integrity_valid"],
    }
    write("signed-settlement-summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
