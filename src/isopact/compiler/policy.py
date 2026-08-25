from __future__ import annotations

from .models import TrustedPolicy


class PolicyCatalog:
    """Trusted in-code policy. Natural language cannot mutate this catalog."""

    def __init__(self) -> None:
        policy = TrustedPolicy(
            policy_id="commerce_missing_order_v1",
            version="1",
            allowed_outcome_type="resolve_missing_order",
            allowed_candidate_concepts=frozenset({"refund", "replacement", "goodwill_credit"}),
            resolution_path_mapping={
                "refund": "successful_refund",
                "replacement": "confirmed_replacement",
                "goodwill_credit": "authorized_goodwill",
            },
            allowed_resolution_paths=frozenset(
                {"successful_refund", "confirmed_replacement", "authorized_goodwill"}
            ),
            exclusive_slot="primary_compensation",
            goodwill_limit_minor_units=5_000,
            goodwill_currency="USD",
            completion_evidence={
                "successful_refund": ("stripe.refund.succeeded",),
                "confirmed_replacement": ("carrier.shipment.accepted",),
            },
            evidence_max_rank={
                "successful_refund": 2,
                "confirmed_replacement": 1,
            },
            human_approval_threshold_minor_units=25_000,
            duplicate_compensation_blocked=True,
        )
        self._mapping = {
            ("demo-retailer", "commerce", "missing_order"): policy,
        }

    def resolve(self, tenant: str, domain: str, case_type: str) -> TrustedPolicy | None:
        return self._mapping.get((tenant, domain, case_type))
