from __future__ import annotations

import hashlib
import json

from .models import CanonicalOperation, OperationIntent, OutcomePact


def _token(value: str) -> str:
    normalized = "_".join(value.strip().lower().split())
    if not normalized:
        raise ValueError("canonical identifier cannot be empty")
    return normalized


def canonicalize(intent: OperationIntent, pact: OutcomePact) -> CanonicalOperation:
    if intent.pact_id != pact.pact_id:
        raise ValueError("intent pact does not match loaded pact")
    if intent.policy != pact.policy:
        raise ValueError("intent policy does not match the pact's pinned policy")
    resolution_path = _token(intent.resolution_path)
    if resolution_path not in pact.allowed_resolution_paths:
        raise ValueError("resolution path is not allowed by pact")
    if (intent.amount is None) == (intent.resource is None):
        raise ValueError("exactly one of amount or resource is required")
    if intent.amount is not None:
        value = f"money:{intent.amount.currency}:{intent.amount.minor_units}"
    else:
        value = f"resource:{_token(intent.resource or '')}"
    identity = {
        "event_type": _token(intent.event_type),
        "pact_id": intent.pact_id.strip(),
        "resolution_path": resolution_path,
        "subject_id": intent.subject_id.strip().upper(),
        "value": value,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return CanonicalOperation(
        pact_id=identity["pact_id"],
        resolution_path=identity["resolution_path"],
        event_type=identity["event_type"],
        subject_id=identity["subject_id"],
        normalized_value=value,
        operation_key=hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        policy=intent.policy,
    )
