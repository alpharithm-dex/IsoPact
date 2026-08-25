from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from isopact.domain.models import Money

from isopact.evidence.identity import stable_id

from .models import ApprovalDecision, ApprovalRequest, ApprovalStatus, AuthorityTier, BoundCompensationAction, CompensationExecutionState, ExecutionDecision, ExecutionResult, ValidatedResolutionPlan
from .registry import CompensationRegistry
from .repository import CompensationRepository
from isopact.observability import telemetry
from time import perf_counter


class AmbiguousCompensationOutcome(RuntimeError): pass
class AuthoritativeCompensationFailure(RuntimeError): pass


class ExternalCompensationPort(Protocol):
    def get_state(self, target_system: str, target_id: str) -> str: ...
    def execute(self, action_type: str, target_id: str) -> dict: ...


class CompensationExecutor:
    def __init__(self, registry: CompensationRegistry, repository: CompensationRepository, external: ExternalCompensationPort) -> None:
        self.registry, self.repository, self.external = registry, repository, external
        self.model_calls = 0

    def prepare(self, plan: ValidatedResolutionPlan, *, now: str, trace_id: str):
        started = perf_counter()
        with telemetry.span("isopact.resolution.validate", **{"isopact.pact_id": plan.pact_id, "isopact.plan.id": plan.plan_id}):
            self.repository.persist_plan(plan)
            result = tuple(self.repository.reserve(plan, action, now, trace_id)[0] for action in plan.actions)
        telemetry.observe("isopact.compensation.validation.duration", (perf_counter() - started) * 1000, compensation_result="VALIDATED")
        return result

    def request_approval(self, plan: ValidatedResolutionPlan, action: BoundCompensationAction, amount: Money, *, now: str) -> ApprovalRequest:
        execution = self.repository.get_execution(action.semantic_operation_key)
        if execution is None or execution.approval_id is None: raise ValueError("action is not awaiting approval")
        approval = ApprovalRequest(execution.approval_id, plan.pact_id, plan.plan_id, execution.execution_id, action.registry_action_id, action.registry_version, action.compensation_action_type or "HUMAN_REVIEW", action.target_id, amount, "Registry requires scoped human approval", action.approval_requirement or "HUMAN", plan.policy_version, now, ApprovalStatus.PENDING)
        existing = self.repository.get_approval(approval.approval_id)
        if existing: return existing
        self.repository.persist_approval(approval); return approval

    def decide_approval(self, approval_id: str, *, approved: bool, decided_by: str, reason: str, now: str) -> ApprovalRequest:
        current = self.repository.get_approval(approval_id)
        if current is None or current.status is not ApprovalStatus.PENDING: raise ValueError("approval is missing or no longer pending")
        decided = replace(current, status=ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED, decided_by=decided_by, decision="APPROVED" if approved else "REJECTED", decision_timestamp=now, decision_reason=reason)
        self.repository.persist_approval(decided)
        decision = ApprovalDecision(stable_id("approval_decision", {"approval_id": current.approval_id, "decision": approved}), current.approval_id, current.pact_id, current.resolution_plan_id, current.compensation_execution_id, current.registry_action_id, current.registry_version, current.target, current.policy_version, approved, decided_by, now, reason)
        self.repository.persist_approval_decision(decision)
        return decided

    def execute(self, plan: ValidatedResolutionPlan, action: BoundCompensationAction, *, now: str) -> ExecutionResult:
        started = perf_counter()
        with telemetry.span("isopact.compensation.execute", **{"isopact.pact_id": plan.pact_id, "isopact.compensation.id": action.registry_action_id}):
            result = self._execute(plan, action, now=now)
            if result.decision is ExecutionDecision.PRECONDITION_FAILED:
                telemetry.log(
                    "WARNING",
                    "compensation precondition failed",
                    **{
                        "isopact.pact_id": plan.pact_id,
                        "isopact.compensation.id": action.registry_action_id,
                        "isopact.compensation.execution_id": result.execution.execution_id,
                        "isopact.compensation.observed_state": result.execution.executed_against_state,
                    },
                )
        telemetry.observe("isopact.resolver.duration", (perf_counter() - started) * 1000, compensation_result=result.decision.value)
        if result.execution.external_call_executed:
            telemetry.add("isopact.compensation.executions", compensation_result=result.decision.value)
        if result.decision is ExecutionDecision.PRECONDITION_FAILED:
            telemetry.add("isopact.compensation.precondition_failures", compensation_result="PRECONDITION_FAILED")
        return result

    def _execute(self, plan: ValidatedResolutionPlan, action: BoundCompensationAction, *, now: str) -> ExecutionResult:
        current = self.repository.get_execution(action.semantic_operation_key)
        if current is None: raise ValueError("compensation authority was not reserved")
        if current.state in {CompensationExecutionState.CONFIRMED, CompensationExecutionState.OUTCOME_UNKNOWN, CompensationExecutionState.EXECUTING}:
            return ExecutionResult(ExecutionDecision.DEFER, current)
        if current.state in {CompensationExecutionState.PRECONDITION_FAILED, CompensationExecutionState.FAILED_AUTHORITATIVELY, CompensationExecutionState.REJECTED}:
            return ExecutionResult(ExecutionDecision.REJECTED, current)
        if action.authority_tier is AuthorityTier.HUMAN_REVIEW_ONLY or action.compensation_action_type is None:
            rejected = replace(current, state=CompensationExecutionState.REJECTED, precondition_result="NO_AUTOMATIC_COMPENSATION", updated_at=now)
            self.repository.update_execution(rejected); return ExecutionResult(ExecutionDecision.REJECTED, rejected)
        if action.authority_tier is AuthorityTier.HUMAN_APPROVAL_REQUIRED:
            approval = self.repository.get_approval(current.approval_id or "")
            if approval is None or approval.status is ApprovalStatus.PENDING:
                return ExecutionResult(ExecutionDecision.APPROVAL_REQUIRED, current)
            if approval.status is not ApprovalStatus.APPROVED or approval.compensation_execution_id != current.execution_id or approval.target != current.target_id or approval.registry_action_id != current.registry_action_id or approval.policy_version != plan.policy_version:
                rejected = replace(current, state=CompensationExecutionState.REJECTED, precondition_result="APPROVAL_REJECTED_OR_SCOPE_MISMATCH", updated_at=now)
                self.repository.update_execution(rejected); return ExecutionResult(ExecutionDecision.REJECTED, rejected)
        definition = self.registry.get(action.registry_action_id)
        with telemetry.span("isopact.compensation.precondition", **{"isopact.pact_id": plan.pact_id, "isopact.compensation.id": action.registry_action_id}):
            state = self.external.get_state(action.target_system, action.target_id)
        if state not in definition.eligible_source_states:
            failed = replace(current, state=CompensationExecutionState.PRECONDITION_FAILED, executed_against_state=state, precondition_result="EXECUTION_STATE_INELIGIBLE", external_call_executed=False, updated_at=now)
            self.repository.update_execution(failed); return ExecutionResult(ExecutionDecision.PRECONDITION_FAILED, failed)
        if "CARRIER_CANCEL_CONFIRMED" in definition.required_preconditions:
            carrier = [item for item in self.repository.executions_for_plan(plan.plan_id) if item.registry_action_id == "carrier_cancel_unaccepted_label_v1"]
            if not carrier or carrier[0].state is not CompensationExecutionState.CONFIRMED:
                failed = replace(current, state=CompensationExecutionState.PRECONDITION_FAILED, executed_against_state=state, precondition_result="DEPENDENCY_NOT_CONFIRMED", external_call_executed=False, updated_at=now)
                self.repository.update_execution(failed); return ExecutionResult(ExecutionDecision.PRECONDITION_FAILED, failed)
        executing = replace(current, state=CompensationExecutionState.EXECUTING, executed_against_state=state, precondition_result="PASS", updated_at=now)
        self.repository.update_execution(executing)  # authority commit precedes external call
        try:
            output = self.external.execute(action.compensation_action_type, action.target_id)
        except AmbiguousCompensationOutcome:
            unknown = replace(executing, state=CompensationExecutionState.OUTCOME_UNKNOWN, external_call_executed=True, updated_at=now)
            self.repository.update_execution(unknown); return ExecutionResult(ExecutionDecision.DEFER, unknown)
        except AuthoritativeCompensationFailure:
            failed = replace(executing, state=CompensationExecutionState.FAILED_AUTHORITATIVELY, external_call_executed=True, updated_at=now)
            self.repository.update_execution(failed); return ExecutionResult(ExecutionDecision.REJECTED, failed)
        confirmed = replace(executing, state=CompensationExecutionState.CONFIRMED, external_call_executed=True, updated_at=now)
        self.repository.update_execution(confirmed); return ExecutionResult(ExecutionDecision.EXECUTE, confirmed, output)

    def reconcile_unknown(self, operation_key: str, *, expected_state: str, evidence_id: str, now: str):
        current = self.repository.get_execution(operation_key)
        if current is None or current.state is not CompensationExecutionState.OUTCOME_UNKNOWN: raise ValueError("execution is not outcome-unknown")
        state = self.external.get_state(current.target_system, current.target_id)
        if state != expected_state: return current
        confirmed = replace(current, state=CompensationExecutionState.CONFIRMED, executed_against_state=state, precondition_result="AUTHORITATIVE_EVIDENCE_CONFIRMED", evidence_ids=tuple(sorted(set(current.evidence_ids) | {evidence_id})), updated_at=now)
        self.repository.update_execution(confirmed); return confirmed
