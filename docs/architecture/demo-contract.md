# Deterministic Demo Contract

## Fixed fixture

Fixture ID: `missing_order_v1`. Virtual time begins at `2026-01-01T12:00:00Z`; runs use a virtual clock and stable identifiers. No Gemini call determines event ordering, agent choice, tool result, or failure.

```yaml
pact_id: pact_order_8472
order_id: ORD-8472
customer_id: CUS-104
ticket_id: JIRA-8472
payment_id: PAY-8472
currency: USD
original_minor_units: 20000
goodwill_limit_minor_units: 5000
allowed_primary_resolutions: [full_refund, replacement]
exclusive_slot: primary_compensation
```

Projected compensation is derived from normalized events: refund A `$200` + replacement `$200` + goodwill `$50` + refund B `$200` = `$650`; projected excess exposure is `$650 - $200 = $450`. Protected replay reports blocked and recovered values separately; it never labels projected exposure as money saved.

## Exact event schedule

| Virtual time | Event ID | Initiator/system | Command or event | Deterministic external result | Baseline effect | Protected effect |
|---:|---|---|---|---|---|---|
| T+000 ms | `e00` | Customer | Missing-order request | Ticket context established | Same | Candidate pact fixture is deterministically validated and activated |
| T+100 ms | `e01` | Support A | `stripe.create_refund` `$200` | `accepted/pending`, `REF-A` | Pending refund recorded | Gateway reserves operation and `primary_compensation`; call allowed; pact `PENDING` |
| T+200 ms | `e02` | Support A | `jira.close_ticket` | Jira returns closed | Ticket becomes closed | Closure blocked/deferred because no rank-1/2 completion evidence; Jira stays awaiting settlement |
| T+300 ms | `e03` | Fulfillment | `carrier.create_label` replacement `$200` | Label `LBL-A` created, not accepted | Replacement projected | Conflicts with held primary slot and is blocked in the fully protected path; for reconciliation demonstration, an explicitly seeded pre-existing label may be observed and handled at `e08` |
| T+350 ms | `e04` | Warehouse | `warehouse.reserve_stock` `$200` | Reservation `STK-A` created | Stock reserved | Blocked with replacement, or observed as pre-existing fixture state in reconciliation variant |
| T+400 ms | `e05` | Retention | `crm.issue_credit` `$50` | Credit `CR-A` confirmed | Authorized goodwill settled | Allowed as separately authorized exception; does not consume primary slot |
| T+500 ms | `e06` | Support B | `stripe.create_refund` `$200` | `accepted/pending`, `REF-B` | Second refund pending | Same semantic operation key as `e01`; downstream call count unchanged; deterministic `BLOCK`/idempotent existing result |
| T+1000 ms | `e07` | Stripe | `stripe.refund.succeeded` for `REF-A` | Rank-1 authoritative evidence | First refund settled; contradictory total remains | Event deduplicated, refund settles, pact re-evaluated |
| T+1100 ms | `e08` | Resolver | Registered replacement cleanup | Label is still unaccepted | No automatic correction | If reconciliation variant seeded `LBL-A`, `carrier.cancel_label` executes after live precondition check; otherwise records no action needed |
| T+1200 ms | `e09` | Resolver | Warehouse cleanup | Stock not dispatched | No correction | If seeded, registered release executes; otherwise no action needed |
| T+1300 ms | `e10` | Receipt service | Closure evaluation | Refund evidence + authorized goodwill + no active duplicate/replacement | Baseline remains contradictory despite Jira closure | Receipt produced; Jira can close; pact `SETTLED` |
| T+1400 ms | `e11` | Stripe | Duplicate delivery of `e07` | Same source event ID | Baseline adapter may expose duplicate delivery | Protected ingestor is a no-op; economics unchanged |

The controlled before/after comparison uses the same schedule and adapter outcomes. Protection changes only Gateway decisions, event admission, reconciliation, and settlement semantics. To demonstrate cancellation specifically without allowing the protected Gateway to create a conflicting replacement, the replay may start with `LBL-A`/`STK-A` as externally pre-existing state discovered at T+300/T+350; the UI and artifact must label this variant. It must not imply that IsoPact authorized those writes.

## Required observable outputs

Each replay emits canonical JSON containing fixture/version, mode, ordered input events, decisions, downstream call counts, system snapshots, normalized economic events, final economic position, lifecycle transitions, conflicts, compensations, evidence, and receipt/verification result.

Baseline assertions:

- Jira is closed while Stripe is pending between `e02` and `e07`.
- Replacement, goodwill, and two refund attempts coexist.
- Computed projected total is `65000` minor units and excess is `45000`.
- Repeated runs produce byte-equivalent canonical result except an explicitly excluded run envelope.

Protected assertions:

- Exactly one semantic `$200` refund reaches Stripe.
- Refund and replacement cannot both acquire `primary_compensation`.
- Goodwill `$50` is allowed as an authorized exception.
- Pending acceptance never settles the pact.
- Settlement occurs only after `e07`, closure checks, and any required registered cleanup.
- Duplicate `e11` changes no economic total.

## Judge-facing causality

The UI must visibly connect each action to its deterministic decision, rule, reservation/slot, downstream call count, evidence rank, economic impact, and lifecycle transition. It must label model fixtures, emulator use, mock services, and real cloud services truthfully.
