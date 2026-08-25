# Deterministic Enterprise Simulator

## Purpose

The Stage 2 simulator demonstrates that locally legitimate service actions can compose into an unsettled business outcome. It is an external-world test harness, not an IsoPact enforcement implementation.

## Architecture

`ScenarioRunner` loads a `Scenario` containing immutable `ScheduledAction` records. `VirtualClock` orders actions and delayed callbacks by `(logical_time, insertion_sequence)` and never sleeps. Each attempt passes through `InterceptionPort`; `AllowAllInterceptor` permits unmanaged behavior. The runner then dispatches to exactly one isolated service and records a structured `ActionResult`.

Each result contains action ID, logical time, actor, target, tool, inputs, interceptor decision, external-call flag, external object ID, immediate result, and scheduled follow-up events. A blocked action never reaches the service.

## Independent services

| Service | Local responsibility | Important state |
|---|---|---|
| Jira-like | Tickets, comments, closure/reopen, future settlement attachment | `OPEN`, `CLOSED`; close time/actor/reason |
| Stripe-like | Refund objects and transport idempotency | `PENDING`, `SUCCEEDED`, `FAILED` |
| Carrier | Replacement labels and shipment progress | `CREATED`, `ACCEPTED`, `DISPATCHED`, `CANCELLED` |
| Warehouse | Replacement stock | `RESERVED`, `RELEASED`, `DISPATCHED` |
| CRM | Authorized goodwill credit | `ISSUED`, `USED`, `REVERSED` |

Jira never queries Stripe. Stripe never queries carrier or CRM. Carrier and warehouse do not infer financial correctness. The runner observes their combined state but does not manufacture the contradiction.

Stripe transport idempotency maps one API key to one refund object. Repeating the same key returns the object; a different key creates another refund even when order, amount, and business purpose match. This is plausible API behavior: transport retry protection is not enterprise semantic idempotency.

## Economic ledger

External service facts append normalized `EconomicEvent` records. The reducer groups events by external object and selects each object's latest state at the requested logical time. It then reports separately:

- `settled_minor_units`: issued/authoritatively completed value;
- `pending_minor_units`: accepted payments awaiting final result;
- `projected_only_minor_units`: non-settled replacement exposure;
- `projected_total_minor_units`: settled + pending + projected-only;
- `projected_excess_minor_units`: max(projected total - original transaction, 0);
- `authorized_exception_minor_units`: independently permitted goodwill included in the position.

Every contributing object is listed in `provenance`. Runtime code contains no `$650` or `$450` result constant.

## Fixed unmanaged timeline

The Stage 0 logical times are preserved without correction: ticket T+0; refund A T+100; Jira closure T+200; replacement T+300; warehouse T+350; goodwill T+400; refund B T+500; refund A settlement T+1000; refund B settlement T+1050. The contradiction checkpoint is T+500, after both refunds are accepted but before settlement.

At that checkpoint, Jira is closed; both refunds are pending and have distinct external IDs; the replacement is created; stock is reserved; and `$50` goodwill is issued. The ledger derives projected compensation of `65000` minor units and projected excess exposure of `45000`.

## Failure capabilities

The simulator represents delayed success, delayed authoritative failure, deterministic timeout, a follow-up event scheduled after Jira closure, and carrier irreversibility after acceptance/dispatch. It does not reconcile any failure in Stage 2.

## Replay interface

```powershell
python scripts/run_scenario.py missing_order_unmanaged
python scripts/run_scenario.py missing_order_preexisting_divergence
python scripts/run_scenario.py missing_order_unmanaged --json
```

Replay files are written under `artifacts/replays/`. The embedded semantic digest hashes canonical replay content before the digest field is added. There are no wall-clock fields or random IDs.
