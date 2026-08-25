# ADR-018: Compensation idempotency

## Status

Accepted for Stage 7.

## Decision

Compensation authority uses a semantic identity over pact, conflict set, registry action/version, and exact target. Firestore creates authority transactionally, commits, then the external call executes outside the transaction.

Execution states distinguish `FAILED_AUTHORITATIVELY` from `OUTCOME_UNKNOWN`. If an action occurs but its response is lost, state remains `OUTCOME_UNKNOWN`; equivalent retries, including after process restart, defer. Trusted source evidence can transition it to `CONFIRMED` without a second external call.

Deterministic top-level lookup pointers locate the authoritative pact-scoped records without collection-group indexes. They grant no authority independently.

## Consequences

The design is fail-closed and may defer legitimate work during ambiguity. It does not claim atomicity across Firestore and external systems.
