from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_id(prefix: str, value: Any, length: int = 32) -> str:
    digest = hashlib.sha256(canonical_json(value).encode()).hexdigest()[:length]
    return f"{prefix}_{digest}"


def logical_evidence_id(
    *,
    pact_id: str,
    source_system: str,
    source_event_id: str,
    evidence_type: str,
    subject: str,
    external_object_id: str | None,
) -> str:
    return stable_id(
        "ev",
        {
            "pact_id": pact_id,
            "source_system": source_system.lower(),
            "source_event_id": source_event_id,
            "evidence_type": evidence_type,
            "subject": subject.lower(),
            "external_object_id": external_object_id,
        },
    )


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()
