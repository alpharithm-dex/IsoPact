from __future__ import annotations

from dataclasses import replace
from typing import Any

from google.cloud import firestore

from isopact.domain.models import ReservationState
from isopact.gateway.activation import ActiveOutcomePact

from .models import (
    ClaimType,
    Conflict,
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


GRAPH_COLLECTIONS = (
    "participants",
    "claims",
    "economic_events",
    "evidence",
    "evidence_deliveries",
    "conflicts",
    "settlement_evaluations",
    "settlement_proofs",
    "invariant_evaluations",
    "invariant_conflicts",
    "economic_snapshots",
    "protection_events",
    "resolution_plans",
    "compensation_executions",
    "approval_requests",
    "approval_decisions",
    "graph_checkpoints",
    "settlement_receipts",
)


class FirestorePactGraphRepository:
    """Per-pact graph repository with atomic evidence dedupe and reduction."""

    def __init__(
        self,
        project: str,
        database: str = "(default)",
        *,
        client: firestore.Client | None = None,
    ) -> None:
        self.project = project
        self.database = database
        self.client = client or firestore.Client(project=project, database=database)
        self.transaction_callback_invocations = 0

    def _pact(self, pact_id: str):
        return self.client.collection("pacts").document(pact_id)

    def activate_graph(self, active_pact: ActiveOutcomePact, now: str) -> None:
        self._pact(active_pact.pact.pact_id).set(
            {
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
            },
            merge=True,
        )

    def add_participant(self, participant: Participant) -> None:
        self._pact(participant.pact_id).collection("participants").document(
            participant.participant_id
        ).set(participant.to_dict())

    def append_claim(self, claim: StateClaim) -> bool:
        pact_ref = self._pact(claim.pact_id)
        claim_ref = pact_ref.collection("claims").document(claim.claim_id)
        transaction = self.client.transaction(max_attempts=10)

        @firestore.transactional
        def append_transaction(txn):
            self.transaction_callback_invocations += 1
            root_snapshot = pact_ref.get(transaction=txn)
            claim_snapshot = claim_ref.get(transaction=txn)
            if not root_snapshot.exists:
                raise KeyError(f"inactive pact {claim.pact_id}")
            if claim_snapshot.exists:
                existing = state_claim_from_dict(claim_snapshot.to_dict())
                if semantic_claim_fingerprint(existing) != semantic_claim_fingerprint(claim):
                    raise ValueError("COMMITTED_CLAIM_SEMANTIC_MUTATION_REFUSED")
                return False
            root = root_snapshot.to_dict()
            revision = int(root.get("graph_revision", 0)) + 1
            claim_sequence = int(root.get("claim_sequence", root.get("claim_count", 0))) + 1
            stored_claim = chain_claim(
                claim, claim_sequence, str(root.get("terminal_claim_hash", GENESIS_CLAIM_HASH))
            )
            if is_primary_resolution(root, claim.resolution_path) and claim.immediate_state in {
                ImmediateState.ACCEPTED,
                ImmediateState.PENDING,
            }:
                root["selected_resolution"] = claim.resolution_path
                if root.get("graph_state") != PactLifecycle.SETTLED.value:
                    root["graph_state"] = PactLifecycle.PENDING.value
            root["graph_revision"] = revision
            root["updated_at"] = claim.ingested_at
            evaluation = settlement_evaluation(root, revision, claim.ingested_at)
            evaluation_ref = pact_ref.collection("settlement_evaluations").document(
                evaluation.evaluation_id
            )
            txn.create(claim_ref, stored_claim.to_dict())
            txn.set(
                pact_ref,
                {
                    "selected_resolution": root.get("selected_resolution"),
                    "graph_state": root["graph_state"],
                    "graph_revision": revision,
                    "claim_sequence": claim_sequence,
                    "claim_count": claim_sequence,
                    "terminal_claim_hash": stored_claim.claim_hash,
                    "updated_at": claim.ingested_at,
                },
                merge=True,
            )
            txn.create(evaluation_ref, evaluation.to_dict())
            return True

        return append_transaction(transaction)

    def ingest_evidence(
        self, evidence: Evidence, delivery: EvidenceDelivery
    ) -> IngestionResult:
        pact_ref = self._pact(evidence.pact_id)
        evidence_ref = pact_ref.collection("evidence").document(evidence.evidence_id)
        delivery_ref = pact_ref.collection("evidence_deliveries").document(
            delivery.delivery_id
        )
        operation_ref = (
            pact_ref.collection("operations").document(evidence.operation_identity)
            if evidence.operation_identity
            else None
        )
        transaction = self.client.transaction(max_attempts=15)

        @firestore.transactional
        def ingest_transaction(txn):
            self.transaction_callback_invocations += 1
            root_snapshot = pact_ref.get(transaction=txn)
            evidence_snapshot = evidence_ref.get(transaction=txn)
            delivery_snapshot = delivery_ref.get(transaction=txn)
            operation_snapshot = operation_ref.get(transaction=txn) if operation_ref else None
            if not root_snapshot.exists:
                raise KeyError(f"inactive pact {evidence.pact_id}")
            root = root_snapshot.to_dict()
            delivery_created = not delivery_snapshot.exists
            if evidence_snapshot.exists:
                if delivery_created:
                    txn.create(delivery_ref, delivery.to_dict())
                resolved = root.get("resolved_operations", {}).get(
                    evidence.operation_identity or ""
                )
                return IngestionResult(
                    evidence.evidence_id,
                    False,
                    delivery_created,
                    False,
                    False,
                    False,
                    False,
                    PactLifecycle(root.get("graph_state", "OPEN")),
                    ImmediateState(resolved["state"]) if resolved else None,
                    int(root.get("graph_revision", 0)),
                )

            revision = int(root.get("graph_revision", 0)) + 1
            operation_key = evidence.operation_identity or f"resolution:{evidence.resolution_path}"
            resolved_operations = dict(root.get("resolved_operations", {}))
            resolved, _ = reduce_operation(resolved_operations.get(operation_key), evidence)
            resolved_operations[operation_key] = resolved
            root["resolved_operations"] = resolved_operations
            if not root.get("selected_resolution") and is_primary_resolution(root, evidence.resolution_path):
                root["selected_resolution"] = evidence.resolution_path
            plan = evaluate_graph(root)
            evaluation = settlement_evaluation(root, revision, evidence.ingested_at)
            old_state = PactLifecycle(root.get("graph_state", "OPEN"))
            settlement_transition = (
                old_state is not PactLifecycle.SETTLED
                and plan.state is PactLifecycle.SETTLED
            )
            settlement_transition_count = int(root.get("settlement_transition_count", 0))
            settlement_evidence_ids = list(root.get("settlement_evidence_ids", []))
            if settlement_transition:
                settlement_transition_count += 1
                settlement_evidence_ids = list(plan.qualifying_evidence_ids)

            claim_id = f"claim_{evidence.evidence_id}"
            claim = StateClaim(
                claim_id=claim_id,
                pact_id=evidence.pact_id,
                claim_type=(
                    ClaimType.AUTHORITATIVE_EVENT
                    if evidence.evidence_rank is EvidenceRank.AUTHORITATIVE_SETTLED_EVENT
                    else ClaimType.VERIFIED_QUERY
                ),
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
            claim = chain_claim(
                claim, claim_sequence, str(root.get("terminal_claim_hash", GENESIS_CLAIM_HASH))
            )
            economic_created = (
                evidence.evidence_rank <= EvidenceRank.VERIFIED_SYSTEM_QUERY
                and evidence.resolved_state
                in {ImmediateState.SUCCEEDED, ImmediateState.FAILED}
            )
            event = None
            if economic_created:
                event = EconomicEvent(
                    event_id=f"economic_{evidence.evidence_id}",
                    pact_id=evidence.pact_id,
                    source_event_id=evidence.source_event_id,
                    kind=evidence.resolution_path,
                    phase=(
                        "SETTLED"
                        if evidence.resolved_state is ImmediateState.SUCCEEDED
                        else "FAILED"
                    ),
                    amount_minor_units=int(root["transaction"]["minor_units"]),
                    currency=str(root["transaction"]["currency"]),
                    subject=evidence.subject,
                    operation_identity=evidence.operation_identity,
                    evidence_ids=(evidence.evidence_id,),
                    occurred_at=evidence.occurred_at,
                )
            conflict = None
            if (
                evidence.resolved_state is ImmediateState.FAILED
                and evidence.evidence_rank <= EvidenceRank.VERIFIED_SYSTEM_QUERY
            ):
                conflict = Conflict(
                    conflict_id=f"failure_{evidence.evidence_id}",
                    pact_id=evidence.pact_id,
                    kind="AUTHORITATIVE_RESOLUTION_FAILURE",
                    status="OPEN",
                    evidence_ids=(evidence.evidence_id,),
                    detected_at=evidence.ingested_at,
                )

            reservation_reconciled = False
            operation_update = None
            if operation_snapshot is not None and operation_snapshot.exists:
                operation_data = operation_snapshot.to_dict()
                operation_state = ReservationState(operation_data["state"])
                target = None
                if (
                    evidence.resolved_state is ImmediateState.SUCCEEDED
                    and operation_state is ReservationState.OUTCOME_UNKNOWN
                ):
                    target = ReservationState.CONFIRMED
                elif (
                    evidence.resolved_state is ImmediateState.FAILED
                    and operation_state is ReservationState.OUTCOME_UNKNOWN
                ):
                    target = ReservationState.FAILED_AUTHORITATIVELY
                if target is not None:
                    operation_update = {
                        "state": target.value,
                        "state_history": [
                            *operation_data.get("state_history", []),
                            target.value,
                        ],
                        "updated_at": evidence.ingested_at,
                    }
                    reservation_reconciled = True

            txn.create(evidence_ref, evidence.to_dict())
            if delivery_created:
                txn.create(delivery_ref, delivery.to_dict())
            txn.create(pact_ref.collection("claims").document(claim_id), claim.to_dict())
            if event is not None:
                txn.create(
                    pact_ref.collection("economic_events").document(event.event_id),
                    event.to_dict(),
                )
            if conflict is not None:
                txn.create(
                    pact_ref.collection("conflicts").document(conflict.conflict_id),
                    conflict.to_dict(),
                )
            txn.create(
                pact_ref.collection("settlement_evaluations").document(
                    evaluation.evaluation_id
                ),
                evaluation.to_dict(),
            )
            if settlement_transition:
                proof = SettlementProof(
                    proof_id=f"settlement_v{root.get('settlement_generation', 1)}",
                    pact_id=evidence.pact_id,
                    selected_resolution=root["selected_resolution"],
                    settlement_status=PactLifecycle.SETTLED,
                    authoritative_evidence_ids=plan.qualifying_evidence_ids,
                    final_external_states={operation_key: resolved["state"]},
                    policy_id=root["policy_id"],
                    policy_version=root["policy_version"],
                    settlement_timestamp=evidence.ingested_at,
                )
                txn.create(
                    pact_ref.collection("settlement_proofs").document(proof.proof_id),
                    proof.to_dict(),
                )
            if operation_update is not None and operation_ref is not None:
                txn.update(operation_ref, operation_update)
            txn.set(
                pact_ref,
                {
                    "selected_resolution": root.get("selected_resolution"),
                    "resolved_operations": resolved_operations,
                    "graph_state": plan.state.value,
                    "graph_revision": revision,
                    "claim_sequence": claim_sequence,
                    "claim_count": claim_sequence,
                    "terminal_claim_hash": claim.claim_hash,
                    "settlement_transition_count": settlement_transition_count,
                    "settlement_evidence_ids": settlement_evidence_ids,
                    "updated_at": evidence.ingested_at,
                },
                merge=True,
            )
            return IngestionResult(
                evidence.evidence_id,
                True,
                delivery_created,
                economic_created,
                True,
                settlement_transition,
                reservation_reconciled,
                plan.state,
                ImmediateState(resolved["state"]),
                revision,
            )

        return ingest_transaction(transaction)

    def snapshot(self, pact_id: str) -> PactGraphSnapshot:
        pact_ref = self._pact(pact_id)
        root_snapshot = pact_ref.get()
        if not root_snapshot.exists:
            raise KeyError(f"unknown pact {pact_id}")
        root = root_snapshot.to_dict()

        def count(collection: str) -> int:
            return sum(1 for _ in pact_ref.collection(collection).stream())

        return PactGraphSnapshot(
            pact_id=pact_id,
            state=PactLifecycle(root.get("graph_state", "OPEN")),
            selected_resolution=root.get("selected_resolution"),
            revision=int(root.get("graph_revision", 0)),
            settlement_transition_count=int(root.get("settlement_transition_count", 0)),
            resolved_operations=dict(root.get("resolved_operations", {})),
            claim_count=count("claims"),
            evidence_count=count("evidence"),
            economic_event_count=count("economic_events"),
            delivery_count=count("evidence_deliveries"),
            participant_count=count("participants"),
            conflict_count=count("conflicts"),
            evaluation_count=count("settlement_evaluations"),
            settlement_proof_count=count("settlement_proofs"),
        )

    def claims_for_pact(self, pact_id: str) -> list[dict[str, Any]]:
        return [
            item.to_dict()
            for item in self._pact(pact_id).collection("claims").order_by("sequence_number").stream()
        ]

    def cleanup_pact(self, pact_id: str) -> None:
        pact_ref = self._pact(pact_id)
        for name in (*GRAPH_COLLECTIONS, "operations", "slots", "executions", "reservation_history"):
            for snapshot in pact_ref.collection(name).stream():
                snapshot.reference.delete()
        pact_ref.delete()
