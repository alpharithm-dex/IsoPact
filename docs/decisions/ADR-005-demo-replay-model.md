# ADR-005: One Replay Model with Interchangeable Interception

- Status: Accepted and implemented for Stage 2
- Date: 2026-08-23

## Context

A manually scripted failing demo and a separately scripted successful demo could hide different inputs, timing, or external behavior. It would not prove that IsoPact changed the outcome.

## Decision

Every fixture is a deterministic action schedule executed by `ScenarioRunner`. Before dispatch, every attempted action passes through `InterceptionPort`. Stage 2 supplies `AllowAllInterceptor`; Stage 4 may supply the IsoPact Gateway adapter without changing the schedule or service implementations.

```text
Scenario schedule -> virtual clock -> ScenarioRunner
                                     -> InterceptionPort
                                        -> AllowAllInterceptor (Stage 2)
                                        -> IsoPact Gateway (Stage 4+)
                                     -> isolated external services
```

Delayed service events use the same virtual clock and stable insertion-order tie breaker. Replay JSON records attempts, decisions, whether the external call ran, immediate response, scheduled follow-ups, normalized economic events, checkpoints, and final service state.

## Fixture boundary

`missing_order_unmanaged` is the prevention-oriented primary comparison. All scheduled agent actions pass through the interception boundary. In Stage 2 they all execute; later, the same attempted replacement and duplicate refund can be blocked before their external calls.

`missing_order_preexisting_divergence` is explicitly reconciliation-oriented. At T+25/T+30, a non-participating external fulfillment path has already created a carrier label and warehouse reservation before future enforcement covers the newly observed case. Those schedule entries are marked `enforcement_boundary: false`. The label remains `CREATED` and stock remains `RESERVED`, making `carrier.cancel_label` and `warehouse.release_stock` potentially eligible later—subject to live precondition checks. IsoPact must not claim it prevented these writes.

## Consequences

The comparison isolates the interceptor as the intentional variable. Service behavior remains plausible and locally scoped. Scenario B cannot be presented as prevention, and Scenario A cannot claim reconciliation of a replacement that was successfully blocked. Fixture/schema changes alter the semantic digest and require updated evidence.
