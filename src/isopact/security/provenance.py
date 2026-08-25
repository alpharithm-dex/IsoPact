from __future__ import annotations

from typing import Any, Iterable, Mapping

from isopact.evidence.canonical import canonical_json_bytes, sha256_hex, verify_claim_chain

from .signing import DocumentSigner, sign_document, verify_signed_document
from isopact.observability import telemetry


def digest_records(records: Iterable[Mapping[str, Any]]) -> str:
    return sha256_hex(canonical_json_bytes(sorted((dict(item) for item in records), key=lambda item: canonical_json_bytes(item))))


def build_checkpoint(
    *, pact_id: str, claims: list[Mapping[str, Any]], evidence_ids: list[str],
    economic_snapshot: Mapping[str, Any], invariant_evaluations: list[Mapping[str, Any]],
    policy_references: list[str], rule_references: list[str], created_at: str,
    signer: DocumentSigner,
) -> dict[str, Any]:
    verification = verify_claim_chain(claims)
    if not verification["claim_chain_valid"]:
        raise ValueError(f"cannot checkpoint invalid claim chain: {verification['reason_codes']}")
    body = {
        "checkpoint_schema_version": "isopact.graph-checkpoint.v1",
        "checkpoint_id": f"checkpoint_{pact_id}_{verification['claim_count']:08d}",
        "pact_id": pact_id,
        "through_sequence": verification["claim_count"],
        "terminal_claim_hash": verification["terminal_claim_hash"],
        "claim_count": verification["claim_count"],
        "evidence_ids_included": sorted(set(evidence_ids)),
        "economic_snapshot_digest": sha256_hex(canonical_json_bytes(dict(economic_snapshot))),
        "invariant_evaluation_digest": digest_records(invariant_evaluations),
        "policy_references": sorted(set(policy_references)),
        "rule_references": sorted(set(rule_references)),
        "created_at": created_at,
    }
    with telemetry.span("isopact.kms.checkpoint.sign", **{"isopact.pact_id": pact_id}):
        return sign_document(body, signer)


def build_settlement_receipt(
    *, pact: Mapping[str, Any], checkpoint: Mapping[str, Any],
    economic_position: Mapping[str, Any], authoritative_evidence_ids: list[str],
    participants: list[Mapping[str, Any]], reconciliation_actions: list[Mapping[str, Any]],
    approval_references: list[str], exceptions: list[Mapping[str, Any]],
    settlement_timestamp: str, signer: DocumentSigner,
    receipt_id: str | None = None,
) -> dict[str, Any]:
    if pact.get("graph_state") != "SETTLED":
        raise ValueError("receipt requires deterministically settled pact")
    body = {
        "receipt_schema_version": "isopact.settlement-receipt.v1",
        "receipt_id": receipt_id or f"receipt_{pact['pact_id']}_{checkpoint['through_sequence']:08d}",
        "pact_id": pact["pact_id"],
        "original_requested_outcome": pact.get("outcome_type", "resolve_missing_order"),
        "subject_identifiers": {
            "order_id": pact.get("order_id"), "customer_id": pact.get("customer_id"),
            "ticket_id": pact.get("ticket_id"),
        },
        "selected_resolution_path": pact["selected_resolution"],
        "final_pact_lifecycle": pact["graph_state"],
        "final_authoritative_external_states": dict(pact.get("resolved_operations", {})),
        "economic_position": dict(economic_position),
        "exceptions": list(exceptions),
        "approval_references": sorted(set(approval_references)),
        "authoritative_evidence_ids": sorted(set(authoritative_evidence_ids)),
        "participants": list(participants),
        "reconciliation_actions": list(reconciliation_actions),
        "policy_version": f"{pact.get('policy_id')}@{pact.get('policy_version')}",
        "rule_versions": [f"{pact.get('evaluation_rule_set_id')}@{pact.get('evaluation_rule_set_version')}"],
        "final_checkpoint": {
            "checkpoint_id": checkpoint["checkpoint_id"],
            "terminal_claim_hash": checkpoint["terminal_claim_hash"],
            "through_sequence": checkpoint["through_sequence"],
        },
        "settlement_timestamp": settlement_timestamp,
    }
    with telemetry.span("isopact.kms.receipt.sign", **{"isopact.pact_id": str(pact["pact_id"]), "isopact.receipt.id": body["receipt_id"]}):
        receipt = sign_document(body, signer)
        telemetry.log(
            "INFO",
            "settlement receipt signed",
            **{
                "isopact.pact_id": str(pact["pact_id"]),
                "isopact.receipt.id": body["receipt_id"],
                "isopact.signing.key_version": str(receipt["signing_key_version"]),
            },
        )
    telemetry.add("isopact.receipts.signed", pact_lifecycle="SETTLED")
    return receipt


def verify_integrity_bundle(
    *, receipt: Mapping[str, Any], checkpoint: Mapping[str, Any],
    claims: list[Mapping[str, Any]], public_keys: Mapping[str, str],
) -> dict[str, Any]:
    reasons: list[str] = []
    receipt_key = public_keys.get(str(receipt.get("signing_key_version")), "")
    checkpoint_key = public_keys.get(str(checkpoint.get("signing_key_version")), "")
    receipt_valid, receipt_reason = verify_signed_document(dict(receipt), receipt_key)
    checkpoint_valid, checkpoint_reason = verify_signed_document(dict(checkpoint), checkpoint_key)
    chain = verify_claim_chain(claims)
    terminal_matches = bool(chain["claim_chain_valid"] and chain["terminal_claim_hash"] == checkpoint.get("terminal_claim_hash") and chain["claim_count"] == checkpoint.get("through_sequence"))
    receipt_checkpoint_matches = receipt.get("final_checkpoint") == {
        "checkpoint_id": checkpoint.get("checkpoint_id"),
        "terminal_claim_hash": checkpoint.get("terminal_claim_hash"),
        "through_sequence": checkpoint.get("through_sequence"),
    }
    receipt_evidence = set(receipt.get("authoritative_evidence_ids", []))
    checkpoint_evidence = set(checkpoint.get("evidence_ids_included", []))
    references_consistent = receipt_evidence.issubset(checkpoint_evidence) and receipt.get("final_pact_lifecycle") == "SETTLED"
    for reason in (receipt_reason, checkpoint_reason, *chain["reason_codes"]):
        if reason:
            reasons.append(reason)
    if not terminal_matches: reasons.append("TERMINAL_HASH_OR_SEQUENCE_MISMATCH")
    if not receipt_checkpoint_matches: reasons.append("RECEIPT_CHECKPOINT_BINDING_MISMATCH")
    if not references_consistent: reasons.append("RECEIPT_REFERENCE_INCONSISTENCY")
    overall = receipt_valid and checkpoint_valid and chain["claim_chain_valid"] and terminal_matches and receipt_checkpoint_matches and references_consistent
    return {
        "receipt_signature_valid": receipt_valid,
        "checkpoint_signature_valid": checkpoint_valid,
        "claim_chain_valid": chain["claim_chain_valid"],
        "terminal_hash_matches": terminal_matches,
        "receipt_checkpoint_matches": receipt_checkpoint_matches,
        "receipt_references_consistent": references_consistent,
        "overall_integrity_valid": overall,
        "reason_codes": sorted(set(reasons)),
    }
