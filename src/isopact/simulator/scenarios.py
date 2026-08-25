from __future__ import annotations

from .models import Scenario, ScheduledAction


REQUEST = (
    "My $200 order never arrived. I was told yesterday that it would be refunded "
    "or replaced. Can someone please resolve this?"
)


def _action(
    action_id: str,
    logical_time: int,
    actor: str,
    target: str,
    tool: str,
    inputs: dict[str, object],
    *,
    enforcement_boundary: bool = True,
) -> ScheduledAction:
    return ScheduledAction(
        action_id, logical_time, actor, target, tool, inputs, enforcement_boundary
    )


def missing_order_unmanaged() -> Scenario:
    return Scenario(
        scenario_id="missing_order_unmanaged",
        description="Legitimate local actions compose into contradictory enterprise state.",
        order_id="ORD-8472",
        customer_id="CUS-104",
        ticket_id="JIRA-8472",
        original_minor_units=20_000,
        currency="USD",
        contradiction_time=500,
        actions=(
            _action("e00", 0, "customer", "jira", "create_ticket", {"request": REQUEST}),
            _action(
                "e01", 100, "support-a", "stripe", "create_refund",
                {"amount_minor_units": 20_000, "currency": "USD", "idempotency_key": "stripe-key-A", "session_id": "support-session-A", "settle_at": 1000, "settlement_outcome": "SUCCEEDED"},
            ),
            _action("e02", 200, "support-a", "jira", "close_ticket", {"reason": "Refund request accepted by payment API", "reference": "REF-001"}),
            _action("e03", 300, "fulfillment", "carrier", "create_label", {"value_minor_units": 20_000, "currency": "USD"}),
            _action("e04", 350, "fulfillment", "warehouse", "reserve_stock", {"resource": "replacement-order", "quantity": 1}),
            _action("e05", 400, "retention", "crm", "issue_credit", {"amount_minor_units": 5_000, "currency": "USD", "authorized": True}),
            _action(
                "e06", 500, "support-b", "stripe", "create_refund",
                {"amount_minor_units": 20_000, "currency": "USD", "idempotency_key": "stripe-key-B", "session_id": "support-session-B", "settle_at": 1050, "settlement_outcome": "SUCCEEDED"},
            ),
        ),
    )


def missing_order_preexisting_divergence() -> Scenario:
    return Scenario(
        scenario_id="missing_order_preexisting_divergence",
        description=(
            "A non-participating fulfillment path created a reversible replacement label "
            "and stock reservation before the case entered the future enforcement boundary."
        ),
        order_id="ORD-8472",
        customer_id="CUS-104",
        ticket_id="JIRA-8472",
        original_minor_units=20_000,
        currency="USD",
        contradiction_time=500,
        actions=(
            _action("p00", 0, "customer", "jira", "create_ticket", {"request": REQUEST}),
            _action("p01", 25, "external-fulfillment", "carrier", "create_label", {"value_minor_units": 20_000, "currency": "USD", "origin": "preexisting_external_path"}, enforcement_boundary=False),
            _action("p02", 30, "external-fulfillment", "warehouse", "reserve_stock", {"resource": "replacement-order", "quantity": 1, "origin": "preexisting_external_path"}, enforcement_boundary=False),
            _action(
                "p03", 100, "support-a", "stripe", "create_refund",
                {"amount_minor_units": 20_000, "currency": "USD", "idempotency_key": "stripe-key-A", "session_id": "support-session-A", "settle_at": 1000, "settlement_outcome": "SUCCEEDED"},
            ),
            _action("p04", 200, "support-a", "jira", "close_ticket", {"reason": "Refund request accepted by payment API", "reference": "REF-001"}),
            _action("p05", 400, "retention", "crm", "issue_credit", {"amount_minor_units": 5_000, "currency": "USD", "authorized": True}),
        ),
    )


def build_scenario(name: str) -> Scenario:
    builders = {
        "missing_order_unmanaged": missing_order_unmanaged,
        "missing_order_preexisting_divergence": missing_order_preexisting_divergence,
    }
    try:
        return builders[name]()
    except KeyError as exc:
        raise ValueError(f"unknown scenario: {name}") from exc

