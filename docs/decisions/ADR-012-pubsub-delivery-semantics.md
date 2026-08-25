# ADR-012: Pub/Sub delivery is not the business idempotency boundary

- Status: Accepted
- Date: 2026-08-23

## Context

Pub/Sub's default delivery is at least once. Acknowledgments are transport operations; redelivery can
occur, and separately published messages for one external event have different message IDs. Even an
exactly-once subscription would not merge two distinct publishes of one business event.

## Decision

Do not enable or depend on exactly-once delivery for Stage 5 correctness. Distinguish:

- Pub/Sub message ID: one transport envelope;
- source event ID: the source system's authoritative event identity;
- IsoPact logical evidence identity: the case-scoped deterministic business evidence key.

Process and commit the idempotent Firestore graph update before acknowledging. On failure before
commit, do not acknowledge; permit redelivery. Application-level evidence identity remains necessary
under every Pub/Sub delivery mode.

## Consequences

- Duplicate/redelivered messages are safe.
- Every delivery remains observable.
- Subscribers must tolerate Firestore aborts and transient failures.
- Transport exactly-once may be evaluated later as an optimization, never as the correctness boundary.
