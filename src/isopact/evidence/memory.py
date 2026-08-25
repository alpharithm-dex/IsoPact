from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from threading import RLock
from typing import Any

from isopact.domain.models import ReservationState
from isopact.gateway.activation import ActiveOutcomePact

from .models import (
    Conflict,
    ClaimType,
    EconomicEvent,
    Evidence,
    EvidenceDelivery,
    EvidenceRank,
    ImmediateState,
    IngestionResult,
    PactGraphSnapshot,
    PactLifecycle,
    Participant,
    SettlementProof,
    StateClaim,
)
from .canonical import GENESIS_CLAIM_HASH, chain_claim, semantic_claim_fingerprint, state_claim_from_dict
from .reducer import evaluate_graph, is_primary_resolution, reduce_operation, settlement_evaluation


class InMemoryPactGraphRepository:
    def __init__(self, reservation_repository: Any | None = None) -> None:
        self._lock = RLock()
        self._reservation_repository = reservation_repository
        self._roots: dict[str, dict[str, Any]] = {}
        self._collections: dict[str, dict[str, dict[str, dict[str, Any]]]] = defaultdict(
            lambda: defaultdict(dict)
        )

    def activate_graph(self, active_pact: ActiveOutcomePact, now: str) -> None:
        with self._lock:
            self._roots[active_pact.pact.pact_id] = {
                **active_pact.to_document(),
                "pact_id": active_pact.pact.pact_id,
                "graph_schema_version": "stage5-pact-graph-v1",
                "graph_state": PactLifecycle.OPEN.value,
                "selected_resolution": None,
                "resolved_operations": {},
                "graph_revision": 0,
                "settlement_generation": 1,
                "settlement_transition_count": 0,
                "settlement_evidence_ids": [],
                "claim_sequence": 0,
                "claim_count": 0,
                "terminal_claim_hash": GENESIS_CLAIM_HASH,
                "created_at": now,
                "updated_at": now,
            }

    def add_participant(self, participant: Participant) -> None:
        with self._lock:
            self._collections[participant.pact_id]["participants"][participant.participant_id] = participant.to_dict()

    def append_claim(self, claim: StateClaim) -> bool:
        with self._lock:
            claims = self._collections[claim.pact_id]["claims"]
            if claim.claim_id in claims:
                existing = state_claim_from_dict(claims[claim.claim_id])
                if semantic_claim_fingerprint(existing) != semantic_claim_fingerprint(claim):
                    raise ValueError("COMMITTED_CLAIM_SEMANTIC_MUTATION_REFUSED")
                return False
            root = self._roots[claim.pact_id]
            revision = int(root["graph_revision"]) + 1
            claim_sequence = int(root.get("claim_sequence", root.get("claim_count", 0))) + 1
            stored_claim = chain_claim(claim, claim_sequence, root.get("terminal_claim_hash", GENESIS_CLAIM_HASH))
            claims[claim.claim_id] = stored_claim.to_dict()
            root["claim_sequence"] = claim_sequence
            root["claim_count"] = claim_sequence
            root["terminal_claim_hash"] = stored_claim.claim_hash
            if is_primary_resolution(root, claim.resolution_path) and claim.immediate_state in {
                ImmediateState.ACCEPTED,
                ImmediateState.PENDING,
            }:
                root["selected_resolution"] = claim.resolution_path
                if root["graph_state"] != PactLifecycle.SETTLED.value:
                    root["graph_state"] = PactLifecycle.PENDING.value
            root["graph_revision"] = revision
            root["updated_at"] = claim.ingested_at
            evaluation = settlement_evaluation(root, revision, claim.ingested_at)
            self._collections[claim.pact_id]["settlement_evaluations"][evaluation.evaluation_id] = evaluation.to_dict()
            return True

    def ingest_evidence(
        self, evidence: Evidence, delivery: EvidenceDelivery
    ) -> IngestionResult:
        with self._lock:
            collections = self._collections[evidence.pact_id]
            delivery_created = delivery.delivery_id not in collections["deliveries"]
            if delivery_created:
                collections["deliveries"][delivery.delivery_id] = delivery.to_dict()
            root = self._roots[evidence.pact_id]
            if evidence.evidence_id in collections["evidence"]:
                resolved = root.get("resolved_operations", {}).get(evidence.operation_identity or "")
                return IngestionResult(
                    evidence.evidence_id, False, delivery_created, False, False, False, False,
                    PactLifecycle(root["graph_state"]),
                    ImmediateState(resolved["state"]) if resolved else None,
                    int(root["graph_revision"]),
                )
            collections["evidence"][evidence.evidence_id] = evidence.to_dict()
            revision = int(root["graph_revision"]) + 1
            operation_key = evidence.operation_identity or f"resolution:{evidence.resolution_path}"
            current = root["resolved_operations"].get(operation_key)
            resolved, changed = reduce_operation(current, evidence)
            root["resolved_operations"][operation_key] = resolved
            if not root.get("selected_resolution") and is_primary_resolution(root, evidence.resolution_path):
                root["selected_resolution"] = evidence.resolution_path
            claim_id = f"claim_{evidence.evidence_id}"
            claim = StateClaim(
                claim_id=claim_id,
                pact_id=evidence.pact_id,
                claim_type=(ClaimType.AUTHORITATIVE_EVENT
                    if evidence.evidence_rank is EvidenceRank.AUTHORITATIVE_SETTLED_EVENT
                    else ClaimType.VERIFIED_QUERY),
                source_system=evidence.source_system,
                source_actor=None,
                subject=evidence.subject,
                external_object_id=evidence.external_object_id,
                operation_identity=evidence.operation_identity,
                resolution_path=evidence.resolution_path,
                immediate_state=evidence.resolved_state,
                evidence_rank=evidence.evidence_rank,
                occurred_at=evidence.occurred_at,
                ingested_at=evidence.ingested_at,
                trace_id=evidence.trace_id,
                source_event_id=evidence.source_event_id,
                references=(evidence.evidence_id,),
            )
            claim_sequence = int(root.get("claim_sequence", root.get("claim_count", 0))) + 1
            claim = chain_claim(claim, claim_sequence, root.get("terminal_claim_hash", GENESIS_CLAIM_HASH))
            collections["claims"][claim_id] = claim.to_dict()
            root["claim_sequence"] = claim_sequence
            root["claim_count"] = claim_sequence
            root["terminal_claim_hash"] = claim.claim_hash
            economic_created = evidence.evidence_rank <= EvidenceRank.VERIFIED_SYSTEM_QUERY and evidence.resolved_state in {ImmediateState.SUCCEEDED, ImmediateState.FAILED}
            if economic_created:
                event = EconomicEvent(
                    event_id=f"economic_{evidence.evidence_id}", pact_id=evidence.pact_id,
                    source_event_id=evidence.source_event_id, kind=evidence.resolution_path,
                    phase="SETTLED" if evidence.resolved_state is ImmediateState.SUCCEEDED else "FAILED",
                    amount_minor_units=int(root["transaction"]["minor_units"]),
                    currency=str(root["transaction"]["currency"]), subject=evidence.subject,
                    operation_identity=evidence.operation_identity, evidence_ids=(evidence.evidence_id,),
                    occurred_at=evidence.occurred_at,
                )
                collections["economic_events"][event.event_id] = event.to_dict()
            reservation_reconciled = self._reconcile_reservation(evidence)
            plan = evaluate_graph(root)
            evaluation = settlement_evaluation(root, revision, evidence.ingested_at)
            old_state = PactLifecycle(root["graph_state"])
            root["graph_state"] = plan.state.value
            settlement_transition = old_state is not PactLifecycle.SETTLED and plan.state is PactLifecycle.SETTLED
            if settlement_transition:
                root["settlement_transition_count"] += 1
                root["settlement_evidence_ids"] = list(plan.qualifying_evidence_ids)
                proof = SettlementProof(
                    proof_id=f"settlement_v{root['settlement_generation']}",
                    pact_id=evidence.pact_id,
                    selected_resolution=root["selected_resolution"],
                    settlement_status=PactLifecycle.SETTLED,
                    authoritative_evidence_ids=plan.qualifying_evidence_ids,
                    final_external_states={operation_key: resolved["state"]},
                    policy_id=root["policy_id"], policy_version=root["policy_version"],
                    settlement_timestamp=evidence.ingested_at,
                )
                collections["settlement_proofs"][proof.proof_id] = proof.to_dict()
            if evidence.resolved_state is ImmediateState.FAILED and evidence.evidence_rank <= 2:
                conflict = Conflict(
                    conflict_id=f"failure_{evidence.evidence_id}", pact_id=evidence.pact_id,
                    kind="AUTHORITATIVE_RESOLUTION_FAILURE", status="OPEN",
                    evidence_ids=(evidence.evidence_id,), detected_at=evidence.ingested_at,
                )
                collections["conflicts"][conflict.conflict_id] = conflict.to_dict()
            root["graph_revision"] = revision
            root["updated_at"] = evidence.ingested_at
            collections["settlement_evaluations"][evaluation.evaluation_id] = evaluation.to_dict()
            return IngestionResult(
                evidence.evidence_id, True, delivery_created, economic_created, True,
                settlement_transition, reservation_reconciled, plan.state,
                ImmediateState(resolved["state"]), revision,
            )

    def _reconcile_reservation(self, evidence: Evidence) -> bool:
        if self._reservation_repository is None or evidence.operation_identity is None:
            return False
        reservation = self._reservation_repository.get(evidence.pact_id, evidence.operation_identity)
        if reservation is None:
            return False
        if evidence.resolved_state is ImmediateState.SUCCEEDED and reservation.state is ReservationState.OUTCOME_UNKNOWN:
            self._reservation_repository.transition(
                evidence.pact_id, evidence.operation_identity,
                ReservationState.OUTCOME_UNKNOWN, ReservationState.CONFIRMED,
            )
            return True
        if evidence.resolved_state is ImmediateState.FAILED and reservation.state is ReservationState.OUTCOME_UNKNOWN:
            self._reservation_repository.transition(
                evidence.pact_id, evidence.operation_identity,
                ReservationState.OUTCOME_UNKNOWN, ReservationState.FAILED_AUTHORITATIVELY,
            )
            return True
        return False

    def snapshot(self, pact_id: str) -> PactGraphSnapshot:
        with self._lock:
            root = self._roots[pact_id]
            collections = self._collections[pact_id]
            return PactGraphSnapshot(
                pact_id=pact_id, state=PactLifecycle(root["graph_state"]),
                selected_resolution=root.get("selected_resolution"), revision=int(root["graph_revision"]),
                settlement_transition_count=int(root["settlement_transition_count"]),
                resolved_operations=dict(root["resolved_operations"]),
                claim_count=len(collections["claims"]), evidence_count=len(collections["evidence"]),
                economic_event_count=len(collections["economic_events"]), delivery_count=len(collections["deliveries"]),
                participant_count=len(collections["participants"]), conflict_count=len(collections["conflicts"]),
                evaluation_count=len(collections["settlement_evaluations"]), settlement_proof_count=len(collections["settlement_proofs"]),
            )

    def cleanup_pact(self, pact_id: str) -> None:
        with self._lock:
            self._roots.pop(pact_id, None)
            self._collections.pop(pact_id, None)

    def claims_for_pact(self, pact_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return sorted(
                self._collections[pact_id]["claims"].values(),
                key=lambda item: int(item["sequence_number"]),
            )
