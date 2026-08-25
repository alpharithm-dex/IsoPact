from __future__ import annotations

from dataclasses import replace

from google.cloud import firestore

from isopact.evidence.identity import stable_id

from .models import EvaluationBundle, ProtectionEvent


class FirestoreInvariantRepository:
    """Atomically stores a complete invariant snapshot; external calls are forbidden here."""

    def __init__(self, project: str, database: str = "(default)", *, client=None) -> None:
        self.client = client or firestore.Client(project=project, database=database)

    def persist(self, bundle: EvaluationBundle, events: tuple[ProtectionEvent, ...] = ()) -> str:
        pact = self.client.collection("pacts").document(bundle.pact_id)
        snapshot_id = stable_id("economic_snapshot", {"pact": bundle.pact_id, "revision": bundle.graph_revision, "rules": f"{bundle.rule_set_id}@{bundle.rule_set_version}"})
        snapshot = pact.collection("economic_snapshots").document(snapshot_id)
        evaluation_refs = [(pact.collection("invariant_evaluations").document(item.evaluation_id), item) for item in bundle.evaluations]
        conflict_refs = [(pact.collection("invariant_conflicts").document(item.conflict_id), item) for item in bundle.conflicts]
        event_refs = [(pact.collection("protection_events").document(item.protection_event_id), item) for item in events]
        transaction = self.client.transaction(max_attempts=10)

        @firestore.transactional
        def write(txn):
            root_snapshot = pact.get(transaction=txn)
            if not root_snapshot.exists:
                raise KeyError(f"inactive pact {bundle.pact_id}")
            root = root_snapshot.to_dict() or {}
            previous_ids = set(root.get("stage6_open_conflict_ids", ()))
            previous = [(pact.collection("invariant_conflicts").document(item), item) for item in sorted(previous_ids)]
            previous_snapshots = {item_id: ref.get(transaction=txn) for ref, item_id in previous}
            current_ids = {item.conflict_id for _, item in conflict_refs}
            for ref, item in evaluation_refs:
                txn.set(ref, item.to_dict(), merge=True)
            for ref, item in conflict_refs:
                old = previous_snapshots.get(item.conflict_id)
                first = (old.to_dict() or {}).get("first_detected_at", item.first_detected_at) if old and old.exists else item.first_detected_at
                txn.set(ref, replace(item, first_detected_at=first).to_dict(), merge=True)
            for ref, item_id in previous:
                old = previous_snapshots[item_id]
                if item_id not in current_ids and old.exists:
                    txn.set(ref, {"status": "RESOLVED", "last_evaluated_at": bundle.evaluated_at}, merge=True)
            for ref, item in event_refs:
                txn.set(ref, item.to_dict(), merge=True)
            txn.set(snapshot, bundle.to_dict(), merge=False)
            txn.set(pact, {
                "stage6_lifecycle": bundle.lifecycle_recommendation.value,
                "stage6_open_conflict_ids": sorted(current_ids),
                "stage6_latest_economic_snapshot_id": snapshot_id,
                "evaluation_rule_set_id": bundle.rule_set_id,
                "evaluation_rule_set_version": bundle.rule_set_version,
                "authorization_policy_version": bundle.authorization_policy_version,
                "updated_at": bundle.evaluated_at,
            }, merge=True)
            return snapshot_id

        return write(transaction)
