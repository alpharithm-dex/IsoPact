from __future__ import annotations

from .models import (
    AuthoritativeCaseContext,
    CompilationResult,
    DeterministicContribution,
    ValidationResult,
    ValidationStatus,
)
from .policy import PolicyCatalog
from .providers import CompilerProvider, CompilerProviderError
from .validator import SemanticValidator


class PactCompiler:
    def __init__(self, provider: CompilerProvider, catalog: PolicyCatalog | None = None) -> None:
        self.provider = provider
        self.validator = SemanticValidator(catalog or PolicyCatalog())

    def compile(
        self, request: str, context: AuthoritativeCaseContext
    ) -> CompilationResult:
        context_text = context.model_dump_json(exclude_none=True)
        try:
            contribution = self.provider.compile(request, context_text)
        except CompilerProviderError as exc:
            return CompilationResult(
                model_contribution=None,
                deterministic_result=ValidationResult(
                    status=ValidationStatus.REJECTED,
                    deterministic_contribution=DeterministicContribution(
                        verified_subjects={},
                        selected_policy_id=None,
                        selected_policy_version=None,
                        assigned_resolution_paths=(),
                        assigned_exclusive_slot=None,
                        assigned_goodwill_limit_minor_units=None,
                        assigned_goodwill_currency=None,
                        assigned_evidence_requirements={},
                        assigned_approval_threshold_minor_units=None,
                        reason_codes=("MODEL_PROVIDER_UNAVAILABLE_OR_INVALID",),
                    ),
                    trusted_draft=None,
                ),
                provider_error=str(exc),
            )
        return CompilationResult(
            model_contribution=contribution,
            deterministic_result=self.validator.validate(contribution.candidate, context),
        )
