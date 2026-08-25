from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any


class WebhookAuthenticationError(ValueError):
    pass


def stripe_style_signature(secret: str, raw_body: bytes, timestamp: int) -> str:
    digest = hmac.new(secret.encode("utf-8"), str(timestamp).encode("ascii") + b"." + raw_body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def verify_stripe_style_signature(
    secret: str, raw_body: bytes, signature_header: str, *, now_epoch: int | None = None,
    tolerance_seconds: int = 300,
) -> None:
    values: dict[str, list[str]] = {}
    for item in signature_header.split(","):
        if "=" in item:
            key, value = item.split("=", 1)
            values.setdefault(key, []).append(value)
    try:
        timestamp = int(values["t"][0])
        signatures = values["v1"]
    except (KeyError, ValueError, IndexError) as exc:
        raise WebhookAuthenticationError("WEBHOOK_SIGNATURE_MALFORMED") from exc
    now = int(time.time()) if now_epoch is None else now_epoch
    if abs(now - timestamp) > tolerance_seconds:
        raise WebhookAuthenticationError("WEBHOOK_TIMESTAMP_OUTSIDE_TOLERANCE")
    expected = stripe_style_signature(secret, raw_body, timestamp).split("v1=", 1)[1]
    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        raise WebhookAuthenticationError("WEBHOOK_SIGNATURE_INVALID")


@dataclass(slots=True)
class AuthenticatedEvidenceIngress:
    pipeline: Any
    secret_provider: Any

    def ingest(self, raw_body: bytes, signature_header: str, *, now_epoch: int | None = None):
        secret = self.secret_provider()
        verify_stripe_style_signature(secret, raw_body, signature_header, now_epoch=now_epoch)
        payload = json.loads(raw_body.decode("utf-8"))
        if str(payload.get("source_system", "")).lower() != "stripe":
            raise WebhookAuthenticationError("WEBHOOK_SOURCE_MISMATCH")
        payload["source_authentication"] = "HMAC_SHA256_VERIFIED"
        return self.pipeline.ingest_event(payload)
