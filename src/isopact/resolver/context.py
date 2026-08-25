from __future__ import annotations

from isopact.invariants.models import EvaluationBundle

from .models import GraphTarget, ResolverCandidate, ResolverContext
from .registry import CompensationRegistry


def build_resolver_context(*, bundle: EvaluationBundle, pact_outcome: str, selected_primary_resolution: str, targets: dict[str, GraphTarget], registry: CompensationRegistry, evidence_summaries: tuple[str, ...] = (), untrusted_text: str = "") -> ResolverContext:
    systems = {item.target_system for item in targets.values()}
    definitions = registry.candidates(systems)
    target_by_action: dict[str, str] = {}
    candidates = []
    for definition in definitions:
        matching = sorted((item for item in targets.values() if item.target_system == definition.target_system and item.forward_action_type == definition.forward_action_type), key=lambda item: item.target_id)
        if not matching: continue
        target_by_action[definition.compensation_id] = matching[0].target_id
        candidates.append(ResolverCandidate(registry_action_id=definition.compensation_id, authority_tier=definition.authority_tier, approval_requirement=definition.approval_requirement, target_system=definition.target_system, eligible_source_states=definition.eligible_source_states, description=definition.description))
    return ResolverContext(
        pact_id=bundle.pact_id, pact_outcome=pact_outcome, selected_primary_resolution=selected_primary_resolution,
        conflict_ids=tuple(item.conflict_id for item in bundle.conflicts),
        conflict_summaries=tuple(f"{item.rule_id}:{item.status}" for item in bundle.conflicts),
        economic_position=bundle.economic_position.to_dict(),
        reversible_external_states={item.target_id: item.current_state for item in targets.values()},
        targets_by_registry_action=target_by_action, available_candidates=tuple(candidates),
        relevant_evidence_summaries=evidence_summaries, untrusted_enterprise_text=untrusted_text,
    )
