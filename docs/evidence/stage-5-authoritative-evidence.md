# Stage 5 evidence — authoritative settlement lifecycle

- Status: PASS
- Live run: `20260823212828_3b1754ac`
- Timestamp: `2026-08-23T21:28:28.345162+00:00`
- Project/database: `isopact-agentic-20260823` / `(default)`
- Pub/Sub topic/subscription: `isopact-stage5-evidence` / `isopact-stage5-evidence-proof`

## Core product moment

The unchanged protected schedule produced nine persisted claims across Gateway actions, API responses,
Jira, an agent assertion, and later authoritative evidence. Before evidence:

- agent: COMPLETE;
- Jira: CLOSED;
- refund immediate response: PENDING (Rank 3);
- IsoPact: PENDING;
- business outcome: UNSETTLED.

After live `stripe.refund.succeeded` evidence, the refund projection became `SUCCEEDED` at Rank 1 and
the pact became `SETTLED` with one settlement transition and one non-cryptographic proof.

## Live Pub/Sub identity proof

Three separately published messages had three different Pub/Sub message IDs but the same source event
ID `evt_stage5_primary_20260823212828_3b1754ac`. The graph persisted three delivery records, one
logical Evidence record, one EconomicEvent, and one settlement transition. Exactly-once delivery was
disabled.

A separate message was deliberately not acknowledged after a simulated pre-commit processing failure.
Pub/Sub redelivered the same message ID; the graph committed, then the subscriber acknowledged it.

## Concurrent ingestion

Twenty-five independent OS processes ingested one logical source event with distinct transport
identities. Final counts were:

- deliveries: 25;
- logical Evidence: 1;
- EconomicEvents: 1;
- effective settlement transitions: 1;
- duplicated economic value: 0.

Firestore invoked transaction callbacks 28 times. An earlier run exposed `409 Aborted` under extreme
contention; bounded idempotent application retry was added, preserving the same source/delivery keys.

## Ordering, failure, query, and restart

- Rank 1 success arrived before older Rank 3 pending evidence and an older pending claim; resolved state
  remained `SUCCEEDED`, with no regression.
- Rank 1 `stripe.refund.failed` left a fresh pact `OPEN`, created one Conflict, and did not settle.
- An authenticated Rank 2 query settled the refund because the pinned policy permits maximum rank 2;
  unit coverage proves it remains pending under strict Rank 1 policy.
- A Stage 4 reservation began `OUTCOME_UNKNOWN`; authoritative success moved it to `CONFIRMED`, a new
  repository/Gateway process still blocked retry, additional refund executions were zero, and the pact
  was `SETTLED`.
- Reloading snapshots through new repository instances preserved state across process boundaries.

## Model independence and safety

Evidence ingestion, ranking, dedupe, monotonic reduction, reservation reconciliation, and settlement
used zero model calls. Secret and dependency scans are recorded by the final Stage 5 verification.
No cross-SaaS ACID or exactly-once business guarantee is claimed.

## Artifacts

- `artifacts/evidence/live-pubsub-settlement.json`
- `artifacts/evidence/live-duplicate-evidence.json`
- `artifacts/evidence/live-out-of-order.json`
- `artifacts/evidence/live-outcome-unknown-resolution.json`
- `artifacts/evidence/summary.json`
- `artifacts/replays/missing_order_stage5_protected.json`
