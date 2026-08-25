# ADR-009: Execute external calls only after reservation commit

- Status: Accepted
- Date: 2026-08-23

## Context

Firestore may invoke a transaction callback more than once when documents change concurrently. An
external API or MCP call inside that callback could therefore run multiple times even if only one
transaction commits.

## Decision

Transaction callbacks may perform only Firestore reads/writes and deterministic computation. Stripe,
carrier, warehouse, CRM, Jira, simulator, and MCP calls execute only after a committed ALLOW and an
`EXECUTING` transition. Immediate outcomes are persisted afterward.

## Distributed-systems windows

```text
Firestore authority committed
  -> process crashes before external call
```

The operation remains `RESERVED` or `EXECUTING`; equivalent attempts defer. Later expiry or evidence
reconciliation may decide whether a safe retry is possible.

```text
External call executed
  -> response lost or process crashes before result persistence
```

When the Gateway observes uncertainty, it persists `OUTCOME_UNKNOWN`, retains exclusive authority,
and defers retries until authoritative evidence reconciles the operation. If persistence itself fails
after the call, the already committed `EXECUTING` state remains fail-closed.

## Consequences

Transaction retries cannot directly duplicate external effects. There remains no atomic transaction
spanning Firestore and external SaaS systems. The state machine deliberately prefers deferred work
over an unsafe duplicate, and Stage 5 supplies later authoritative evidence reconciliation.
