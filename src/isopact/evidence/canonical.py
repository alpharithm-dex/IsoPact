from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any, Iterable, Mapping

from .models import StateClaim


CLAIM_SCHEMA_VERSION = "isopact.stateclaim.v1"
GENESIS_CLAIM_HASH = hashlib.sha256(b"isopact:stateclaim:genesis:v1").hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    """IsoPact Canonical JSON v1: UTF-8 I-JSON, sorted keys, no whitespace/floats."""
    _reject_floats(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _reject_floats(value: Any) -> None:
    if isinstance(value, float):
        raise TypeError("canonical security documents do not permit floating-point values")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical JSON object keys must be strings")
            _reject_floats(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_floats(item)


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalized_claim_payload(claim: StateClaim) -> dict[str, Any]:
    if claim.normalized_payload:
        return dict(claim.normalized_payload)
    return {
        "evidence_rank": int(claim.evidence_rank),
        "external_object_id": claim.external_object_id,
        "immediate_state": claim.immediate_state.value,
        "resolution_path": claim.resolution_path,
        "subject": claim.subject,
    }


def canonical_claim_body(claim: StateClaim) -> dict[str, Any]:
    payload = normalized_claim_payload(claim)
    payload_digest = claim.normalized_payload_hash or sha256_hex(canonical_json_bytes(payload))
    return {
        "agent_identity": claim.agent_identity,
        "claim_id": claim.claim_id,
        "claim_schema_version": claim.claim_schema_version,
        "claim_type": claim.claim_type.value,
        "evidence_references": sorted(claim.references),
        "ingestion_timestamp": claim.ingested_at,
        "logical_timestamp": claim.occurred_at,
        "normalized_claim_payload": payload,
        "normalized_payload_hash": payload_digest,
        "operation_identity": claim.operation_identity,
        "pact_id": claim.pact_id,
        "policy_references": sorted(claim.policy_references),
        "previous_claim_hash": claim.previous_claim_hash,
        "protected_references": sorted(claim.protected_references),
        "rule_references": sorted(claim.rule_references),
        "sequence_number": claim.sequence,
        "source_actor": claim.source_actor,
        "source_event_id": claim.source_event_id,
        "source_system": claim.source_system,
        "trace_id": claim.trace_id,
    }


def chain_claim(claim: StateClaim, sequence: int, previous_hash: str) -> StateClaim:
    if sequence < 1:
        raise ValueError("claim sequence must be positive")
    if len(previous_hash) != 64:
        raise ValueError("previous claim hash must be a SHA-256 hex digest")
    payload = normalized_claim_payload(claim)
    payload_digest = sha256_hex(canonical_json_bytes(payload))
    prepared = replace(
        claim,
        claim_schema_version=CLAIM_SCHEMA_VERSION,
        sequence=sequence,
        previous_claim_hash=previous_hash,
        claim_hash="",
        normalized_payload=payload,
        normalized_payload_hash=payload_digest,
    )
    digest = sha256_hex(bytes.fromhex(previous_hash) + canonical_json_bytes(canonical_claim_body(prepared)))
    return replace(prepared, claim_hash=digest)


def state_claim_from_dict(data: Mapping[str, Any]) -> StateClaim:
    from .models import ClaimType, EvidenceRank, ImmediateState

    return StateClaim(
        claim_id=str(data["claim_id"]), pact_id=str(data["pact_id"]),
        claim_type=ClaimType(data["claim_type"]), source_system=str(data["source_system"]),
        source_actor=data.get("source_actor"), subject=str(data.get("subject") or data.get("normalized_payload", {}).get("subject") or data.get("normalized_claim_payload", {}).get("subject") or ""),
        external_object_id=data.get("external_object_id") or data.get("normalized_payload", {}).get("external_object_id") or data.get("normalized_claim_payload", {}).get("external_object_id"),
        operation_identity=data.get("operation_identity"), resolution_path=data.get("resolution_path") or data.get("normalized_payload", {}).get("resolution_path") or data.get("normalized_claim_payload", {}).get("resolution_path"),
        immediate_state=ImmediateState(data.get("immediate_state") or data.get("normalized_payload", {}).get("immediate_state") or data.get("normalized_claim_payload", {}).get("immediate_state")),
        evidence_rank=EvidenceRank(int(data.get("evidence_rank") or data.get("normalized_payload", {}).get("evidence_rank") or data.get("normalized_claim_payload", {}).get("evidence_rank"))),
        occurred_at=str(data.get("occurred_at") or data.get("logical_timestamp")), ingested_at=str(data.get("ingested_at") or data.get("ingestion_timestamp")),
        trace_id=str(data["trace_id"]), source_event_id=data.get("source_event_id"),
        references=tuple(data.get("references") or data.get("evidence_references", ())),
        sequence=int(data.get("sequence") or data.get("sequence_number", 0)),
        claim_schema_version=str(data.get("claim_schema_version", CLAIM_SCHEMA_VERSION)),
        previous_claim_hash=str(data.get("previous_claim_hash", "")), claim_hash=str(data.get("claim_hash", "")),
        agent_identity=data.get("agent_identity"), policy_references=tuple(data.get("policy_references", ())),
        rule_references=tuple(data.get("rule_references", ())),
        normalized_payload=dict(data.get("normalized_payload") or data.get("normalized_claim_payload", {})),
        normalized_payload_hash=str(data.get("normalized_payload_hash", "")),
        protected_references=tuple(data.get("protected_references", ())),
    )


def verify_claim_chain(claims: Iterable[StateClaim | Mapping[str, Any]]) -> dict[str, Any]:
    materialized = [item if isinstance(item, StateClaim) else state_claim_from_dict(item) for item in claims]
    # Artifact order is part of the proof. Repository readers must supply
    # sequence order; silently sorting here would conceal a reordered history.
    ordered = materialized
    reasons: list[str] = []
    previous = GENESIS_CLAIM_HASH
    if len(ordered) != len({item.sequence for item in ordered}):
        reasons.append("DUPLICATE_SEQUENCE")
    for expected, claim in enumerate(ordered, start=1):
        if claim.sequence != expected:
            reasons.append("NON_CONTIGUOUS_SEQUENCE")
        if claim.previous_claim_hash != previous:
            reasons.append("PREVIOUS_HASH_MISMATCH")
        payload_digest = sha256_hex(canonical_json_bytes(normalized_claim_payload(claim)))
        if payload_digest != claim.normalized_payload_hash:
            reasons.append("PAYLOAD_HASH_MISMATCH")
        expected_hash = sha256_hex(bytes.fromhex(claim.previous_claim_hash) + canonical_json_bytes(canonical_claim_body(replace(claim, claim_hash="")))) if len(claim.previous_claim_hash) == 64 else ""
        if claim.claim_hash != expected_hash:
            reasons.append("CLAIM_HASH_MISMATCH")
        previous = claim.claim_hash
    return {
        "claim_chain_valid": not reasons,
        "claim_count": len(ordered),
        "sequence_range": [1, len(ordered)] if ordered else [],
        "terminal_claim_hash": previous,
        "reason_codes": sorted(set(reasons)),
    }


def semantic_claim_fingerprint(claim: StateClaim) -> str:
    body = canonical_claim_body(replace(
        claim, sequence=0, previous_claim_hash="", claim_hash="", normalized_payload_hash=""
    ))
    body.pop("sequence_number")
    body.pop("previous_claim_hash")
    body["normalized_payload_hash"] = sha256_hex(canonical_json_bytes(body["normalized_claim_payload"]))
    return sha256_hex(canonical_json_bytes(body))
