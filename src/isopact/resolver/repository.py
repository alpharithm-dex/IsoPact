from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from isopact.domain.models import Money
from isopact.evidence.identity import stable_id

from .models import ApprovalDecision, ApprovalRequest, ApprovalStatus, AuthorityTier, BoundCompensationAction, CompensationExecution, CompensationExecutionState, ValidatedResolutionPlan


class CompensationRepository(Protocol):
    def persist_plan(self, plan: ValidatedResolutionPlan) -> None: ...
    def reserve(self, plan: ValidatedResolutionPlan, action: BoundCompensationAction, now: str, trace_id: str) -> tuple[CompensationExecution, bool]: ...
    def get_execution(self, operation_key: str) -> CompensationExecution | None: ...
    def update_execution(self, execution: CompensationExecution) -> None: ...
    def executions_for_plan(self, plan_id: str) -> tuple[CompensationExecution, ...]: ...
    def persist_approval(self, approval: ApprovalRequest) -> None: ...
    def get_approval(self, approval_id: str) -> ApprovalRequest | None: ...
    def persist_approval_decision(self, decision: ApprovalDecision) -> None: ...


def new_execution(plan: ValidatedResolutionPlan, action: BoundCompensationAction, now: str, trace_id: str) -> CompensationExecution:
    execution_id = stable_id("compensation_execution", {"operation_key": action.semantic_operation_key})
    state = CompensationExecutionState.AWAITING_APPROVAL if action.authority_tier is AuthorityTier.HUMAN_APPROVAL_REQUIRED else CompensationExecutionState.AUTHORIZED
    approval_id = stable_id("approval", {"pact": plan.pact_id, "plan": plan.plan_id, "execution": execution_id, "action": action.registry_action_id, "target": action.target_id, "policy": plan.policy_version}) if state is CompensationExecutionState.AWAITING_APPROVAL else None
    return CompensationExecution(execution_id, plan.pact_id, plan.conflict_ids, plan.plan_id, action.registry_action_id, action.registry_version, action.target_system, action.target_id, action.semantic_operation_key, state, action.authority_tier, approval_id, action.planned_against_state, action.validated_against_state, None, None, False, (), action.economic_effect_category, trace_id, now)


class MemoryCompensationRepository:
    def __init__(self) -> None:
        self.plans: dict[str, ValidatedResolutionPlan] = {}
        self.executions: dict[str, CompensationExecution] = {}
        self.approvals: dict[str, ApprovalRequest] = {}
        self.approval_decisions: dict[str, ApprovalDecision] = {}

    def persist_plan(self, plan): self.plans[plan.plan_id] = plan
    def reserve(self, plan, action, now, trace_id):
        existing = self.executions.get(action.semantic_operation_key)
        if existing: return existing, False
        item = new_execution(plan, action, now, trace_id); self.executions[action.semantic_operation_key] = item; return item, True
    def get_execution(self, operation_key): return self.executions.get(operation_key)
    def update_execution(self, execution): self.executions[execution.semantic_operation_key] = execution
    def executions_for_plan(self, plan_id): return tuple(sorted((item for item in self.executions.values() if item.plan_id == plan_id), key=lambda item: item.registry_action_id))
    def persist_approval(self, approval): self.approvals[approval.approval_id] = approval
    def get_approval(self, approval_id): return self.approvals.get(approval_id)
    def persist_approval_decision(self, decision): self.approval_decisions[decision.approval_decision_id] = decision


def execution_from_dict(data: dict) -> CompensationExecution:
    return CompensationExecution(
        execution_id=data["execution_id"], pact_id=data["pact_id"], conflict_ids=tuple(data["conflict_ids"]), plan_id=data["plan_id"], registry_action_id=data["registry_action_id"], registry_version=data["registry_version"], target_system=data["target_system"], target_id=data["target_id"], semantic_operation_key=data["semantic_operation_key"], state=CompensationExecutionState(data["state"]), authority_tier=AuthorityTier(data["authority_tier"]), approval_id=data.get("approval_id"), planned_against_state=data["planned_against_state"], validated_against_state=data["validated_against_state"], executed_against_state=data.get("executed_against_state"), precondition_result=data.get("precondition_result"), external_call_executed=bool(data["external_call_executed"]), evidence_ids=tuple(data.get("evidence_ids", ())), economic_effect_category=data["economic_effect_category"], trace_id=data["trace_id"], updated_at=data["updated_at"])


def approval_from_dict(data: dict) -> ApprovalRequest:
    return ApprovalRequest(data["approval_id"], data["pact_id"], data["resolution_plan_id"], data["compensation_execution_id"], data["registry_action_id"], data["registry_version"], data["requested_action"], data["target"], Money(**data["economic_impact"]), data["reason"], data["required_authority"], data["policy_version"], data["requested_at"], ApprovalStatus(data["status"]), data.get("decided_by"), data.get("decision"), data.get("decision_timestamp"), data.get("decision_reason"))


class FirestoreCompensationRepository:
    def __init__(self, project: str, database: str = "(default)", *, client=None) -> None:
        self.client = client or firestore.Client(project=project, database=database)

    def _pact(self, pact_id): return self.client.collection("pacts").document(pact_id)
    def persist_plan(self, plan):
        batch = self.client.batch()
        batch.set(self._pact(plan.pact_id).collection("resolution_plans").document(plan.plan_id), plan.to_dict())
        batch.set(self.client.collection("resolution_plan_index").document(plan.plan_id), {"pact_id": plan.pact_id, "plan_id": plan.plan_id})
        batch.commit()
    def reserve(self, plan, action, now, trace_id):
        ref = self._pact(plan.pact_id).collection("compensation_executions").document(action.semantic_operation_key)
        index_ref = self.client.collection("compensation_operation_index").document(action.semantic_operation_key)
        transaction = self.client.transaction(max_attempts=10)
        @firestore.transactional
        def reserve_txn(txn):
            snapshot = ref.get(transaction=txn)
            index_snapshot = index_ref.get(transaction=txn)
            if snapshot.exists: return execution_from_dict(snapshot.to_dict()), False
            if index_snapshot.exists and index_snapshot.to_dict().get("pact_id") != plan.pact_id:
                raise ValueError("semantic compensation identity collision")
            item = new_execution(plan, action, now, trace_id)
            txn.create(ref, item.to_dict())
            txn.set(index_ref, {"pact_id": plan.pact_id, "semantic_operation_key": action.semantic_operation_key})
            return item, True
        return reserve_txn(transaction)
    def get_execution(self, operation_key):
        pointer = self.client.collection("compensation_operation_index").document(operation_key).get()
        if not pointer.exists: return None
        snapshot = self._pact(pointer.to_dict()["pact_id"]).collection("compensation_executions").document(operation_key).get()
        return execution_from_dict(snapshot.to_dict()) if snapshot.exists else None
    def update_execution(self, execution): self._pact(execution.pact_id).collection("compensation_executions").document(execution.semantic_operation_key).set(execution.to_dict(), merge=True)
    def executions_for_plan(self, plan_id):
        pointer = self.client.collection("resolution_plan_index").document(plan_id).get()
        if not pointer.exists: return ()
        matches = self._pact(pointer.to_dict()["pact_id"]).collection("compensation_executions").where(filter=FieldFilter("plan_id", "==", plan_id)).stream()
        return tuple(sorted((execution_from_dict(item.to_dict()) for item in matches), key=lambda item: item.registry_action_id))
    def persist_approval(self, approval):
        batch = self.client.batch()
        batch.set(self._pact(approval.pact_id).collection("approval_requests").document(approval.approval_id), approval.to_dict())
        batch.set(self.client.collection("approval_request_index").document(approval.approval_id), {"pact_id": approval.pact_id, "approval_id": approval.approval_id})
        batch.commit()
    def get_approval(self, approval_id):
        pointer = self.client.collection("approval_request_index").document(approval_id).get()
        if not pointer.exists: return None
        snapshot = self._pact(pointer.to_dict()["pact_id"]).collection("approval_requests").document(approval_id).get()
        return approval_from_dict(snapshot.to_dict()) if snapshot.exists else None
    def persist_approval_decision(self, decision): self._pact(decision.pact_id).collection("approval_decisions").document(decision.approval_decision_id).set(decision.to_dict())
