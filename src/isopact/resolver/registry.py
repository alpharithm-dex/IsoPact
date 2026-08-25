from __future__ import annotations

from .models import AuthorityTier, CompensationDefinition


class CompensationRegistry:
    def __init__(self, definitions: tuple[CompensationDefinition, ...]) -> None:
        self._definitions = {item.compensation_id: item for item in definitions}
        if len(self._definitions) != len(definitions):
            raise ValueError("duplicate compensation ID")

    def get(self, compensation_id: str) -> CompensationDefinition:
        try:
            return self._definitions[compensation_id]
        except KeyError as exc:
            raise ValueError(f"unregistered compensation {compensation_id}") from exc

    def candidates(self, target_systems: set[str]) -> tuple[CompensationDefinition, ...]:
        return tuple(sorted((item for item in self._definitions.values() if item.target_system in target_systems), key=lambda item: (item.mandatory_order, item.compensation_id)))

    @property
    def definitions(self) -> tuple[CompensationDefinition, ...]:
        return tuple(sorted(self._definitions.values(), key=lambda item: item.compensation_id))


def default_compensation_registry() -> CompensationRegistry:
    return CompensationRegistry((
        CompensationDefinition("carrier_cancel_unaccepted_label_v1", "1", "commerce", "carrier.create_label", "carrier.cancel_label", "carrier", ("CREATED",), ("ACCEPTED", "DISPATCHED", "CANCELLED"), ("TARGET_BELONGS_TO_PACT", "STATE_CREATED"), AuthorityTier.AUTOMATIC, None, "BIND_CONFLICT_SHIPMENT_ID", ("carrier.label.cancelled",), "PACT_CONFLICT_ACTION_TARGET_REGISTRY_VERSION", "PRIMARY_REPLACEMENT_REMOVAL", "Cancel an unaccepted replacement label.", 10),
        CompensationDefinition("warehouse_release_reserved_stock_v1", "1", "commerce", "warehouse.reserve_stock", "warehouse.release_stock", "warehouse", ("RESERVED",), ("DISPATCHED", "RELEASED"), ("TARGET_BELONGS_TO_PACT", "STATE_RESERVED", "CARRIER_CANCEL_CONFIRMED"), AuthorityTier.AUTOMATIC, None, "BIND_CONFLICT_STOCK_RESERVATION_ID", ("warehouse.stock.released",), "PACT_CONFLICT_ACTION_TARGET_REGISTRY_VERSION", "PRIMARY_REPLACEMENT_REMOVAL", "Release stock after carrier cancellation.", 20),
        CompensationDefinition("jira_reopen_without_settlement_v1", "1", "commerce", "jira.close_ticket", "jira.reopen_ticket", "jira", ("CLOSED",), ("OPEN",), ("TARGET_BELONGS_TO_PACT", "SETTLEMENT_EVIDENCE_MISSING"), AuthorityTier.AUTOMATIC, None, "BIND_PACT_TICKET_ID", ("jira.ticket.open",), "PACT_CONFLICT_ACTION_TARGET_REGISTRY_VERSION", "OPERATIONAL_METADATA", "Reopen a closed ticket lacking settlement evidence.", 30),
        CompensationDefinition("crm_reverse_unused_goodwill_v1", "1", "commerce", "crm.issue_credit", "crm.reverse_credit", "crm", ("ISSUED", "UNUSED", "REVERSIBLE"), ("USED", "REVERSED"), ("TARGET_BELONGS_TO_PACT", "CREDIT_UNUSED"), AuthorityTier.HUMAN_APPROVAL_REQUIRED, "COMMERCE_FINANCIAL_REVERSAL_APPROVER", "BIND_CONFLICT_CREDIT_ID", ("crm.credit.reversed",), "PACT_PLAN_ACTION_TARGET_POLICY_VERSION", "GOODWILL_REVERSAL", "Reverse an unused goodwill credit with approval.", 40),
        CompensationDefinition("stripe_settled_refund_no_automatic_v1", "1", "commerce", "stripe.create_refund", None, "stripe", (), ("SUCCEEDED",), ("HUMAN_REVIEW",), AuthorityTier.HUMAN_REVIEW_ONLY, "HUMAN_REVIEW", "BIND_CONFLICT_REFUND_ID", (), "NONE", "NO_AUTOMATIC_COMPENSATION", "A settled refund has no automatic monetary reversal.", 50),
    ))
