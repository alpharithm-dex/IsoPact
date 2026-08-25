# Typed Compensation Registry

The trusted registry is immutable code/config, versioned independently from model output. Every definition records forward and compensation actions, target system, eligible/forbidden states, preconditions, authority and approval, deterministic binding, post-execution evidence, semantic idempotency scope, economic category, description, and mandatory order.

Version 1 contains:

- `carrier_cancel_unaccepted_label_v1`: automatic only from `CREATED`; cancellation evidence required.
- `warehouse_release_reserved_stock_v1`: automatic only from `RESERVED`, after carrier cancellation confirmation; release evidence required.
- `jira_reopen_without_settlement_v1`: automatic metadata reconciliation from `CLOSED` when settlement evidence is absent.
- `crm_reverse_unused_goodwill_v1`: reversible unused/issued credit, but human approval is mandatory.
- `stripe_settled_refund_no_automatic_v1`: explicit human-review-only entry with no compensation action.

Semantic compensation identity hashes pact, conflicts, registry action, target, and registry version. Transport/session IDs do not grant new authority. `CONFIRMED`, `EXECUTING`, and `OUTCOME_UNKNOWN` retries defer. Authoritative evidence may reconcile `OUTCOME_UNKNOWN`; timeout alone cannot release authority.

For the missing-order recovery, the policy requires both carrier `CANCELLED` and warehouse `RELEASED` evidence before the $200 replacement exposure is removed. Carrier success with warehouse failure is partial: economic and operational conflicts remain open and recovered value stays $0.
