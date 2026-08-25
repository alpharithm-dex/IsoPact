from __future__ import annotations

from isopact.evidence.identity import stable_id

from .models import AuthorityTier, BoundCompensationAction, GraphTarget, PlanValidationStatus, ResolutionProposal, ResolverContext, ValidatedResolutionPlan
from .registry import CompensationRegistry
from isopact.observability import telemetry
from time import perf_counter


class DeterministicPlanValidator:
    def __init__(self, registry: CompensationRegistry) -> None:
        self.registry = registry
        self.model_calls = 0

    def validate(self, *, context: ResolverContext, proposal: ResolutionProposal, targets: dict[str, GraphTarget], active_conflict_ids: set[str], policy_version: str, now: str) -> ValidatedResolutionPlan:
        started = perf_counter()
        with telemetry.span("isopact.resolution.validate", **{"isopact.pact_id": context.pact_id}):
            result = self._validate(context=context, proposal=proposal, targets=targets, active_conflict_ids=active_conflict_ids, policy_version=policy_version, now=now)
        telemetry.observe("isopact.compensation.validation.duration", (perf_counter() - started) * 1000, compensation_result=result.status.value)
        return result

    def _validate(self, *, context: ResolverContext, proposal: ResolutionProposal, targets: dict[str, GraphTarget], active_conflict_ids: set[str], policy_version: str, now: str) -> ValidatedResolutionPlan:
        candidate = proposal.candidate
        reasons: list[str] = []
        rejected = False
        if candidate.pact_id != context.pact_id: reasons.append("PACT_MISMATCH"); rejected = True
        if not candidate.conflict_ids or not set(candidate.conflict_ids) <= active_conflict_ids: reasons.append("CONFLICT_MISSING_OR_STALE"); rejected = True
        available = {item.registry_action_id for item in context.available_candidates}
        selected = candidate.selected_registry_action_ids
        if not selected or len(set(selected)) != len(selected): reasons.append("EMPTY_OR_DUPLICATE_ACTION_SELECTION"); rejected = True
        if not set(selected) <= available: reasons.append("UNREGISTERED_OR_UNAVAILABLE_ACTION"); rejected = True
        definitions = []
        for action_id in selected:
            try: definitions.append(self.registry.get(action_id))
            except ValueError: reasons.append("UNREGISTERED_ACTION"); rejected = True
        if any(item.authority_tier is AuthorityTier.HUMAN_REVIEW_ONLY for item in definitions) and len(definitions) > 1:
            reasons.append("HUMAN_REVIEW_ACTION_CANNOT_BE_COMBINED"); rejected = True
        needs_approval = any(item.authority_tier is AuthorityTier.HUMAN_APPROVAL_REQUIRED for item in definitions)
        if needs_approval and not candidate.requires_human_attention:
            reasons.append("APPROVAL_BYPASS_ATTEMPT"); rejected = True
        bound: list[BoundCompensationAction] = []
        for definition in sorted(definitions, key=lambda item: (item.mandatory_order, item.compensation_id)):
            target_id = context.targets_by_registry_action.get(definition.compensation_id)
            target = targets.get(target_id or "")
            if target is None or target.pact_id != context.pact_id:
                reasons.append("TARGET_BINDING_FAILED"); rejected = True; continue
            if target.target_system != definition.target_system or target.forward_action_type != definition.forward_action_type:
                reasons.append("FORWARD_ACTION_OR_TARGET_MISMATCH"); rejected = True; continue
            if definition.authority_tier is not AuthorityTier.HUMAN_REVIEW_ONLY and target.current_state not in definition.eligible_source_states:
                reasons.append("VALIDATION_PRECONDITION_FAILED"); rejected = True; continue
            operation_key = stable_id("compensation_operation", {"pact_id": context.pact_id, "conflicts": sorted(candidate.conflict_ids), "registry_action": definition.compensation_id, "target": target.target_id, "registry_version": definition.registry_version})
            bound.append(BoundCompensationAction(len(bound)+1, definition.compensation_id, definition.registry_version, definition.compensation_action_type, definition.target_system, target.target_id, definition.forward_action_type, definition.authority_tier, definition.approval_requirement, target.current_state, target.current_state, operation_key, definition.required_evidence_after_execution, definition.economic_effect_category))
        plan_id = stable_id("resolution_plan", {"pact_id": context.pact_id, "conflicts": sorted(candidate.conflict_ids), "actions": list(selected), "targets": {item.registry_action_id: item.target_id for item in bound}, "policy": policy_version})
        if rejected:
            status = PlanValidationStatus.REJECTED
        elif any(item.authority_tier is AuthorityTier.HUMAN_REVIEW_ONLY for item in definitions):
            status = PlanValidationStatus.HUMAN_REVIEW_REQUIRED; reasons.append("NO_AUTOMATIC_COMPENSATION")
        elif needs_approval:
            status = PlanValidationStatus.VALID_REQUIRES_APPROVAL; reasons.append("SCOPED_APPROVAL_REQUIRED")
        else:
            status = PlanValidationStatus.VALID_AUTOMATIC; reasons.append("REGISTERED_AUTOMATIC_PLAN_VALID")
        return ValidatedResolutionPlan(plan_id, context.pact_id, tuple(sorted(candidate.conflict_ids)), status, tuple(bound if not rejected else ()), tuple(reasons), policy_version, "1", proposal.metadata.provider, proposal.metadata.model, candidate.model_dump(mode="json"), now, 0)
