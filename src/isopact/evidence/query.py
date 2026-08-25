from __future__ import annotations

from typing import Any

from .identity import logical_evidence_id, payload_hash
from .models import Authenticity, Evidence, EvidenceRank, ImmediateState
from .pipeline import utc_now


class StripeQueryEvidenceProvider:
    """Trusted adapter over a simulated authenticated payment-system state query."""

    def __init__(self, refunds: dict[str, dict[str, Any]]) -> None:
        self.refunds = refunds

    def query(
        self,
        *,
        pact_id: str,
        refund_id: str,
        order_id: str,
        operation_identity: str | None,
        observed_at: str,
        trace_id: str,
    ) -> Evidence:
        refund = self.refunds[refund_id]
        state = str(refund["state"])
        state_map = {
            "SUCCEEDED": ("stripe.refund.succeeded", ImmediateState.SUCCEEDED),
            "FAILED": ("stripe.refund.failed", ImmediateState.FAILED),
            "PENDING": ("stripe.refund.pending", ImmediateState.PENDING),
        }
        evidence_type, resolved_state = state_map[state]
        source_event_id = f"verified-query:{refund_id}:{state}:{observed_at}"
        raw = {"refund_id": refund_id, "state": state, "observed_at": observed_at}
        return Evidence(
            evidence_id=logical_evidence_id(
                pact_id=pact_id,
                source_system="stripe",
                source_event_id=source_event_id,
                evidence_type=evidence_type,
                subject=order_id,
                external_object_id=refund_id,
            ),
            pact_id=pact_id,
            source_system="stripe",
            source_event_id=source_event_id,
            evidence_type=evidence_type,
            evidence_rank=EvidenceRank.VERIFIED_SYSTEM_QUERY,
            authenticity=Authenticity.VERIFIED,
            subject=order_id,
            external_object_id=refund_id,
            operation_identity=operation_identity,
            operation_attempt=1,
            source_sequence=None,
            resolution_path="successful_refund",
            resolved_state=resolved_state,
            payload_hash=payload_hash(raw),
            occurred_at=observed_at,
            ingested_at=utc_now(),
            verification_mechanism="AUTHENTICATED_SYSTEM_OF_RECORD_QUERY",
            trace_id=trace_id,
        )
