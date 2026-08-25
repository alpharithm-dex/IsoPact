from __future__ import annotations

import hashlib
import json

from .models import (
    AuthoritativeCaseContext,
    CandidateOutcomePact,
    DeterministicContribution,
    ValidationResult,
    ValidationStatus,
    ValidatedOutcomePactDraft,
)
from .policy import PolicyCatalog


class SemanticValidator:
    def __init__(self, catalog: PolicyCatalog) -> None:
        self.catalog = catalog

    def validate(
        self, candidate: CandidateOutcomePact, context: AuthoritativeCaseContext
    ) -> ValidationResult:
        reasons: list[str] = []
        policy = self.catalog.resolve(context.tenant, context.domain, context.case_type)
        if policy is None:
            return self._failure(ValidationStatus.REJECTED, ["UNKNOWN_POLICY_MAPPING"])
        if candidate.ambiguities:
            return self._failure(
                ValidationStatus.NEEDS_CLARIFICATION,
                ["UNRESOLVED_AMBIGUITY"],
                policy.policy_id,
                policy.version,
            )
        if candidate.candidate_outcome_type != policy.allowed_outcome_type:
            reasons.append("UNKNOWN_OUTCOME_TYPE")

        known_subjects: dict[str, str] = {"ticket_id": context.ticket_id}
        known_order_ids = {order.order_id for order in context.orders}
        known_customer_ids = {order.customer_id for order in context.orders}
        extracted = {ref.subject_type: ref.value for ref in candidate.subject_references}
        order_id = extracted.get("order_id")
        customer_id = extracted.get("customer_id")
        ticket_id = extracted.get("ticket_id")
        if not order_id or order_id not in known_order_ids:
            reasons.append("UNKNOWN_ORDER_SUBJECT")
        if not customer_id or customer_id not in known_customer_ids:
            reasons.append("UNKNOWN_CUSTOMER_SUBJECT")
        if ticket_id is not None and ticket_id != context.ticket_id:
            reasons.append("UNKNOWN_TICKET_SUBJECT")
        order = next((item for item in context.orders if item.order_id == order_id), None)
        if order is not None and customer_id != order.customer_id:
            reasons.append("CUSTOMER_ORDER_MISMATCH")
        if order is not None:
            known_subjects.update(order_id=order.order_id, customer_id=order.customer_id)

        concepts = tuple(dict.fromkeys(candidate.candidate_resolution_paths))
        unsupported = set(concepts) - policy.allowed_candidate_concepts
        if unsupported:
            reasons.append("UNSUPPORTED_RESOLUTION_CONCEPT")
        if (
            "refund" in concepts
            and "replacement" in concepts
            and candidate.requested_resolution_semantics.strip().lower() in {"both", "both_required", "refund_and_replacement"}
        ):
            reasons.append("EXCLUSIVE_RESOLUTIONS_REQUESTED_AS_MANDATORY")
        trusted_paths = tuple(
            dict.fromkeys(
                policy.resolution_path_mapping[concept]
                for concept in concepts
                if concept in policy.resolution_path_mapping
            )
        )
        if any(path not in policy.allowed_resolution_paths for path in trusted_paths):
            reasons.append("POLICY_PATH_LOOKUP_FAILED")

        allowed_evidence_concepts = {"refund_status", "shipment_status", "goodwill_status"}
        if set(candidate.candidate_evidence_requirements) - allowed_evidence_concepts:
            reasons.append("INVENTED_EVIDENCE_SOURCE")

        if candidate.extracted_amount is not None and order is not None:
            if candidate.extracted_amount.currency != order.currency:
                reasons.append("UNSUPPORTED_CURRENCY")
            if candidate.extracted_amount.minor_units != order.captured_minor_units:
                reasons.append("AMOUNT_CONTEXT_MISMATCH")

        if reasons:
            return self._failure(
                ValidationStatus.REJECTED, reasons, policy.policy_id, policy.version, known_subjects
            )

        draft_seed = json.dumps(
            {"policy": policy.policy_id, "subjects": known_subjects, "outcome": candidate.candidate_outcome_type},
            sort_keys=True,
            separators=(",", ":"),
        )
        draft = ValidatedOutcomePactDraft(
            draft_id="draft_" + hashlib.sha256(draft_seed.encode()).hexdigest()[:16],
            outcome_type=policy.allowed_outcome_type,
            subjects=known_subjects,
            requested_resolution_semantics=candidate.requested_resolution_semantics,
            allowed_resolution_paths=trusted_paths,
            exclusive_slot=policy.exclusive_slot,
            goodwill_limit_minor_units=policy.goodwill_limit_minor_units,
            goodwill_currency=policy.goodwill_currency,
            completion_evidence=policy.completion_evidence,
            human_approval_threshold_minor_units=policy.human_approval_threshold_minor_units,
            duplicate_compensation_blocked=policy.duplicate_compensation_blocked,
            policy_id=policy.policy_id,
            policy_version=policy.version,
        )
        contribution = DeterministicContribution(
            verified_subjects=known_subjects,
            selected_policy_id=policy.policy_id,
            selected_policy_version=policy.version,
            assigned_resolution_paths=trusted_paths,
            assigned_exclusive_slot=policy.exclusive_slot,
            assigned_goodwill_limit_minor_units=policy.goodwill_limit_minor_units,
            assigned_goodwill_currency=policy.goodwill_currency,
            assigned_evidence_requirements=policy.completion_evidence,
            assigned_approval_threshold_minor_units=policy.human_approval_threshold_minor_units,
            reason_codes=("CANDIDATE_SEMANTICS_VALIDATED", "TRUSTED_POLICY_ENRICHED"),
        )
        return ValidationResult(
            status=ValidationStatus.VALID,
            deterministic_contribution=contribution,
            trusted_draft=draft,
        )

    @staticmethod
    def _failure(
        status: ValidationStatus,
        reasons: list[str],
        policy_id: str | None = None,
        policy_version: str | None = None,
        subjects: dict[str, str] | None = None,
    ) -> ValidationResult:
        return ValidationResult(
            status=status,
            deterministic_contribution=DeterministicContribution(
                verified_subjects=subjects or {},
                selected_policy_id=policy_id,
                selected_policy_version=policy_version,
                assigned_resolution_paths=(),
                assigned_exclusive_slot=None,
                assigned_goodwill_limit_minor_units=None,
                assigned_goodwill_currency=None,
                assigned_evidence_requirements={},
                assigned_approval_threshold_minor_units=None,
                reason_codes=tuple(reasons),
            ),
            trusted_draft=None,
        )

