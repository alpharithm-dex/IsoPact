from __future__ import annotations

from typing import Any


def build_case_chronicle(root: dict[str, Any], collections: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Derive a safe timeline from authoritative Pact Graph facts; persist nothing."""
    entries: list[dict[str, Any]] = []
    for claim in collections.get("claims", []):
        payload = claim.get("normalized_payload") or claim.get("normalized_claim_payload") or {}
        refs = list(claim.get("references") or claim.get("evidence_references") or [])
        entries.append({
            "entry_id": claim.get("claim_id"), "logical_time": claim.get("occurred_at") or claim.get("logical_timestamp"),
            "observed_time": claim.get("ingested_at") or claim.get("ingestion_timestamp"), "pact_id": claim.get("pact_id"),
            "actor": claim.get("source_actor") or claim.get("agent_identity"), "actor_role": payload.get("role"),
            "category": claim.get("claim_type"), "action": payload.get("action_kind") or claim.get("subject"),
            "target_system": claim.get("source_system"), "gateway_decision": payload.get("authorization_result"),
            "reason_code": payload.get("reason_code"), "external_execution": payload.get("external_state") is not None,
            "immediate_state": claim.get("immediate_state") or payload.get("immediate_state"),
            "evidence_rank": claim.get("evidence_rank"), "trace_id": claim.get("trace_id"),
            "stateclaim": {"sequence": claim.get("sequence_number") or claim.get("sequence"), "hash": claim.get("claim_hash")},
            "caused_by": refs, "confirmed_by": refs if int(claim.get("evidence_rank", 99)) == 1 else [],
        })
    for conflict in collections.get("conflicts", []) + collections.get("invariant_conflicts", []):
        entries.append({"entry_id": conflict.get("conflict_id"), "logical_time": conflict.get("detected_at") or conflict.get("created_at"), "observed_time": conflict.get("updated_at"), "pact_id": root.get("pact_id"), "category": "CONFLICT", "action": conflict.get("rule_id"), "conflict": conflict.get("status") or conflict.get("severity"), "blocked_by": conflict.get("evidence_ids") or [], "reconciled_by": conflict.get("resolution_evidence_ids") or []})
    entries.sort(key=lambda e: (str(e.get("logical_time") or ""), int((e.get("stateclaim") or {}).get("sequence") or 0), str(e.get("entry_id") or "")))
    receipts = collections.get("settlement_receipts", [])
    return {"pact_id": root.get("pact_id"), "current_lifecycle": root.get("graph_state"), "selected_resolution": root.get("selected_resolution"), "entries": entries, "conflicts": [e for e in entries if e.get("category") == "CONFLICT"], "trace_ids": sorted({e["trace_id"] for e in entries if e.get("trace_id")}), "receipt_verification": [{"receipt_id": r.get("receipt_id"), "issuance_status": r.get("issuance_status"), "signing_key_version": r.get("signing_key_version")} for r in receipts]}
