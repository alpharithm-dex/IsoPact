from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .identity import logical_evidence_id, payload_hash, stable_id
from .models import (
    Authenticity,
    ClaimType,
    Evidence,
    EvidenceDelivery,
    EvidenceRank,
    ImmediateState,
    IngestionResult,
    PactLifecycle,
    Participant,
    StateClaim,
)
from .repository import PactGraphRepository
from isopact.observability import telemetry
from time import perf_counter


EVENT_RULES = {
    "stripe.refund.succeeded": ("stripe", "successful_refund", ImmediateState.SUCCEEDED, EvidenceRank.AUTHORITATIVE_SETTLED_EVENT),
    "stripe.refund.failed": ("stripe", "successful_refund", ImmediateState.FAILED, EvidenceRank.AUTHORITATIVE_SETTLED_EVENT),
    "stripe.refund.reversed": ("stripe", "successful_refund", ImmediateState.REVERSED, EvidenceRank.AUTHORITATIVE_SETTLED_EVENT),
    "stripe.refund.pending": ("stripe", "successful_refund", ImmediateState.PENDING, EvidenceRank.ACCEPTED_PENDING_RESPONSE),
    "carrier.shipment.accepted": ("carrier", "confirmed_replacement", ImmediateState.SUCCEEDED, EvidenceRank.AUTHORITATIVE_SETTLED_EVENT),
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def direct_delivery(source_event_id: str, received_at: str) -> EvidenceDelivery:
    return EvidenceDelivery(
        delivery_id=stable_id("delivery", {"mechanism": "DIRECT", "source_event_id": source_event_id}),
        delivery_mechanism="DIRECT",
        pubsub_message_id=None,
        publish_timestamp=None,
        received_at=received_at,
    )


class EvidencePipeline:
    def __init__(self, repository: PactGraphRepository) -> None:
        self.repository = repository
        self.model_calls = 0

    def ingest_event(
        self,
        payload: dict[str, Any],
        delivery: EvidenceDelivery | None = None,
        causal_links: tuple[Any, ...] = (),
    ) -> IngestionResult:
        event_type = str(payload["event_type"])
        try:
            expected_source, resolution_path, resolved_state, rank = EVENT_RULES[event_type]
        except KeyError as exc:
            raise ValueError(f"untrusted or unsupported evidence type: {event_type}") from exc
        source_system = str(payload["source_system"]).lower()
        if source_system != expected_source:
            raise ValueError("event source does not match trusted evidence mapping")
        pact_id = str(payload["pact_id"])
        source_event_id = str(payload["source_event_id"])
        subject = str(payload["subject"])
        external_object_id = (
            str(payload["external_object_id"])
            if payload.get("external_object_id") is not None
            else None
        )
        ingested_at = str(payload.get("ingested_at") or utc_now())
        evidence_id = logical_evidence_id(
            pact_id=pact_id,
            source_system=source_system,
            source_event_id=source_event_id,
            evidence_type=event_type,
            subject=subject,
            external_object_id=external_object_id,
        )
        evidence = Evidence(
            evidence_id=evidence_id,
            pact_id=pact_id,
            source_system=source_system,
            source_event_id=source_event_id,
            evidence_type=event_type,
            evidence_rank=rank,
            authenticity=Authenticity.VERIFIED,
            subject=subject,
            external_object_id=external_object_id,
            operation_identity=(
                str(payload["operation_identity"])
                if payload.get("operation_identity")
                else None
            ),
            operation_attempt=int(payload.get("operation_attempt", 1)),
            source_sequence=(int(payload["source_sequence"]) if payload.get("source_sequence") is not None else None),
            resolution_path=resolution_path,
            resolved_state=resolved_state,
            payload_hash=payload_hash(payload),
            occurred_at=str(payload["occurred_at"]),
            ingested_at=ingested_at,
            verification_mechanism=(
                "SIGNED_OR_AUTHENTICATED_SYSTEM_EVENT"
                if rank is EvidenceRank.AUTHORITATIVE_SETTLED_EVENT
                else "IMMEDIATE_API_STATE"
            ),
            trace_id=str(payload.get("trace_id", f"trace-{source_event_id}")),
        )
        started = perf_counter()
        with telemetry.span("isopact.evidence.ingest", links=causal_links, **{"isopact.pact_id": pact_id, "isopact.evidence.rank": int(rank), "isopact.evidence.source": source_system}):
            with telemetry.span("isopact.evidence.reduce", **{"isopact.pact_id": pact_id, "isopact.evidence.rank": int(rank)}):
                with telemetry.span("isopact.settlement.evaluate", **{"isopact.pact_id": pact_id}):
                    result = self.repository.ingest_evidence(evidence, delivery or direct_delivery(source_event_id, ingested_at))
            telemetry.log(
                "INFO",
                "evidence ingestion decision",
                **{
                    "isopact.pact_id": pact_id,
                    "isopact.evidence.id": evidence_id,
                    "isopact.evidence.created": result.logical_evidence_created,
                    "isopact.evidence.rank": int(rank),
                },
            )
            if result.settlement_transition_created:
                telemetry.log(
                    "INFO",
                    "settlement lifecycle transition",
                    **{
                        "isopact.pact_id": pact_id,
                        "isopact.pact.lifecycle": result.pact_state.value,
                        "isopact.evidence.id": evidence_id,
                    },
                )
        labels = {"evidence_rank": str(int(rank))}
        telemetry.add("isopact.evidence.received", **labels)
        if not result.logical_evidence_created:
            telemetry.add("isopact.evidence.duplicates_deduped", **labels)
        telemetry.observe("isopact.evidence.processing.duration", (perf_counter() - started) * 1000, **labels)
        if result.settlement_transition_created:
            telemetry.add("isopact.settlement.transitions", pact_lifecycle=result.pact_state.value)
        return result

    def ingest_verified_query(
        self, evidence: Evidence, delivery: EvidenceDelivery | None = None
    ) -> IngestionResult:
        if evidence.evidence_rank is not EvidenceRank.VERIFIED_SYSTEM_QUERY:
            raise ValueError("verified query adapter must emit Rank 2 evidence")
        if evidence.authenticity is not Authenticity.VERIFIED:
            raise ValueError("verified query evidence must be verified")
        return self.repository.ingest_evidence(
            evidence,
            delivery or direct_delivery(evidence.source_event_id, evidence.ingested_at),
        )

    def record_claim(self, claim: StateClaim) -> bool:
        started = perf_counter()
        with telemetry.span("isopact.claim.append", **{"isopact.pact_id": claim.pact_id, "isopact.evidence.rank": int(claim.evidence_rank)}):
            result = self.repository.append_claim(claim)
        telemetry.observe("isopact.claim.append.duration", (perf_counter() - started) * 1000, evidence_rank=str(int(claim.evidence_rank)))
        return result

    def record_text_claim(
        self,
        *,
        pact_id: str,
        source_kind: str,
        source_actor: str,
        text: str,
        occurred_at: str,
        trace_id: str,
    ) -> bool:
        source_kind = source_kind.lower()
        if source_kind in {"agent", "agent_summary"}:
            rank = EvidenceRank.AGENT_INTERPRETATION
            claim_type = ClaimType.AGENT_ASSERTION
        else:
            rank = EvidenceRank.UNVERIFIED_NATURAL_LANGUAGE
            claim_type = ClaimType.SYSTEM_STATE
        claim_id = stable_id(
            "claim",
            {
                "pact_id": pact_id,
                "source_kind": source_kind,
                "source_actor": source_actor,
                "text": text,
                "occurred_at": occurred_at,
            },
        )
        return self.repository.append_claim(
            StateClaim(
                claim_id=claim_id,
                pact_id=pact_id,
                claim_type=claim_type,
                source_system=source_kind,
                source_actor=source_actor,
                subject=text,
                external_object_id=None,
                operation_identity=None,
                resolution_path=None,
                immediate_state=ImmediateState.COMPLETE,
                evidence_rank=rank,
                occurred_at=occurred_at,
                ingested_at=utc_now(),
                trace_id=trace_id,
            )
        )


def record_replay_claims(
    pipeline: EvidencePipeline,
    pact_id: str,
    replay: dict[str, Any],
) -> dict[str, Any]:
    for result in replay["action_results"]:
        actor = result["actor"]
        pipeline.repository.add_participant(
            Participant(
                participant_id=f"participant_{actor}",
                pact_id=pact_id,
                kind="AGENT" if actor != "customer" else "HUMAN",
                display_name=actor,
                authenticated_principal=actor,
                roles=("scenario-participant",),
            )
        )
        decision = result["interceptor_decision"]
        state = ImmediateState.UNKNOWN
        claim_type = ClaimType.GATEWAY_AUTHORIZATION
        rank = EvidenceRank.AGENT_INTERPRETATION
        object_state = result.get("immediate_result", {}).get("object", {}).get("state")
        if result["external_call_executed"]:
            claim_type = ClaimType.API_RESPONSE
            rank = EvidenceRank.ACCEPTED_PENDING_RESPONSE
            if object_state == "PENDING":
                state = ImmediateState.PENDING
            elif result["target_system"] == "jira" and result["tool"] == "close_ticket":
                state = ImmediateState.CLOSED
            else:
                state = ImmediateState.ACCEPTED
        resolution_path = None
        if result["target_system"] == "stripe" and result["tool"] == "create_refund":
            resolution_path = "successful_refund"
        elif result["target_system"] in {"carrier", "warehouse"}:
            resolution_path = "confirmed_replacement"
        pipeline.record_claim(
            StateClaim(
                claim_id=f"claim_replay_{result['action_id']}",
                pact_id=pact_id,
                claim_type=claim_type,
                source_system=result["target_system"],
                source_actor=actor,
                subject="ORD-8472",
                external_object_id=result.get("external_object_id"),
                operation_identity=decision.get("operation_identity"),
                resolution_path=resolution_path,
                immediate_state=state,
                evidence_rank=rank,
                occurred_at=f"logical:{result['logical_time']:08d}",
                ingested_at=utc_now(),
                trace_id=decision.get("trace_id") or f"trace-{result['action_id']}",
                references=(),
            )
        )
    pipeline.record_text_claim(
        pact_id=pact_id,
        source_kind="agent",
        source_actor="support-a",
        text="Ticket resolved; refund complete.",
        occurred_at="logical:00000201",
        trace_id="trace-agent-complete",
    )
    snapshot = pipeline.repository.snapshot(pact_id)
    jira = replay["final"]["services"]["jira"]["JIRA-8472"]
    return {
        "agent_status": "COMPLETE",
        "jira_state": jira["status"],
        "refund_immediate_state": "PENDING",
        "immediate_evidence_rank": int(EvidenceRank.ACCEPTED_PENDING_RESPONSE),
        "isopact_pact_state": snapshot.state.value,
        "business_settled": snapshot.state.value == PactLifecycle.SETTLED.value,
    }
