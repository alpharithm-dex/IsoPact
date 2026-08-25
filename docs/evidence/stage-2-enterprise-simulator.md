# Stage 2 Evidence: Deterministic Enterprise Simulator

- Status: PASS
- Recorded: 2026-08-23
- Runtime: CPython 3.12.7 on Windows
- Scope: deterministic in-process external service adapters and replay runner

## Exact commands and results

```powershell
python -m unittest discover -s tests -v
```

```text
Ran 23 tests in 0.306s
OK
METRIC same_transport_key_external_objects=1 different_keys_same_business_outcome_objects=2
METRIC replay_runs=20 unique_semantic_digests=1 digest=8a658e271d8ec01ad6152fc475bd374ab3b9bf3bf94062cad42b1063c29eddf3
```

The 23 total includes all 13 Stage 1 regression tests plus 10 Stage 2 tests.

```powershell
python scripts/run_scenario.py missing_order_unmanaged
python scripts/run_scenario.py missing_order_preexisting_divergence
```

```text
scenario=missing_order_unmanaged
semantic_digest=8a658e271d8ec01ad6152fc475bd374ab3b9bf3bf94062cad42b1063c29eddf3
projected_total_minor_units=65000
projected_excess_minor_units=45000

scenario=missing_order_preexisting_divergence
semantic_digest=7012777a31a694b59f1a82ced1fb3d05f93628f932d706a067c470c857968c9e
projected_total_minor_units=45000
projected_excess_minor_units=25000
```

## Unmanaged contradiction at T+500

| Observation | Measured value |
|---|---|
| Jira | `CLOSED` |
| Refund A / `REF-001` | `PENDING` |
| Refund B / `REF-002` | `PENDING` |
| Replacement / `SHIP-001` | `CREATED` |
| Warehouse / `STK-001` | `RESERVED` |
| Goodwill / `CR-001` | `ISSUED`, `5000 USD` minor units |

Delayed `REF-001` settlement occurs at T+1000, after Jira closed at T+200. `REF-002` settles at T+1050. The contradiction checkpoint correctly describes refunds as pending rather than settled.

## Economic derivation

At T+500, the latest normalized event for each value-bearing external object is:

| Object | Event | Phase | Contribution |
|---|---|---|---:|
| `REF-001` | `REFUND_PENDING` | `PENDING` | 20000 |
| `SHIP-001` | `REPLACEMENT_CREATED` | `PROJECTED` | 20000 |
| `CR-001` | `GOODWILL_CREDIT_ISSUED` | `SETTLED` and authorized exception | 5000 |
| `REF-002` | `REFUND_PENDING` | `PENDING` | 20000 |

Derived totals: settled `5000`; pending `40000`; projected-only `20000`; projected total `65000`; original transaction `20000`; projected excess `45000`. Provenance amounts sum to `65000`. No result total is hard-coded in simulator runtime code.

## Transport idempotency

Two calls with `same-key` produced one external refund object. A third call describing the same order/amount/outcome but using `different-key` and another agent produced a second refund object. API idempotency protects a transport retry; IsoPact's later semantic identity protects the business outcome across independent agents.

## Pre-existing divergence fixture

In `missing_order_preexisting_divergence`, `p01` and `p02` are explicitly marked outside the future enforcement boundary. A non-participating fulfillment path creates `SHIP-001` at T+25 and `STK-001` at T+30 before the case is governed. At the checkpoint, the label is `CREATED` and stock is `RESERVED`; later registered candidates are `carrier.cancel_label` and `warehouse.release_stock`, subject to rechecked preconditions. This fixture proves reconciliation setup, not prevention.

## Other capability evidence

- Delayed successful and failed refunds transition from `PENDING` only when virtual time reaches the scheduled callback.
- Carrier cancellation succeeds only in `CREATED`; acceptance makes it ineligible, and dispatch is explicitly represented.
- Deterministic service timeout yields `TIMEOUT` with no refund object.
- A substitute interceptor blocks `e03` before dispatch and leaves carrier state empty, demonstrating interchangeability without implementing Stage 4 policy.
- Service objects contain only their own state (plus clock/ledger dependencies for event-producing services); no service holds another service reference.
- Source scan for model/provider names in `src/isopact/simulator` returns zero matches.

## Artifacts

- `artifacts/replays/missing_order_unmanaged.json`
- `artifacts/replays/missing_order_preexisting_divergence.json`

File SHA-256 values from the measured run:

```text
8B4474E40532AAF07E1DF42305367A13470E5AEE3FE0EFB55DE4D2A52B5CC5D4  missing_order_unmanaged.json
761BD3AC821631E2135EB4AA19F10707C359B5B639DA81D51D4554CD49D3BB02  missing_order_preexisting_divergence.json
```

## Limitations

- Services are deterministic in-process adapters, not networked MCP servers or replicas of vendor APIs.
- The semantic digest proves equality for 20 runs in this runtime; it is not a cross-language canonicalization guarantee.
- No Gateway, IsoPact invariant, Firestore, Pub/Sub, model, agent, or resolver behavior is claimed.
- Timeout currently occurs before object creation; ambiguous post-write timeout behavior remains represented by the Stage 1 core, not this adapter fixture.
