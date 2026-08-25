# ADR-004: Ambiguous Execution Outcomes

- Status: Accepted and implemented for Stage 1
- Date: 2026-08-23

## Context

A downstream write can occur before its response is lost. Treating the timeout as failure and releasing authority can cause duplicate value movement on retry.

## Decision

The Stage 1 reservation lifecycle is:

```text
RESERVED -> EXECUTING -> CONFIRMED
                      -> FAILED_AUTHORITATIVELY
                      -> OUTCOME_UNKNOWN
OUTCOME_UNKNOWN -> CONFIRMED | FAILED_AUTHORITATIVELY
CONFIRMED -> REVERSED
RESERVED -> EXPIRED
FAILED_AUTHORITATIVELY -> RESERVED (explicit retry; same operation key, new attempt)
```

`OUTCOME_UNKNOWN` is a durable fail-closed state. An equivalent attempt receives `DEFER / EXTERNAL_OUTCOME_UNKNOWN`; the operation key and exclusive slot remain held. It is never converted to failure because of elapsed time alone.

Later authoritative evidence resolves it. A verified system-of-record success moves it to `CONFIRMED`, permanently blocking duplicate execution. A verified failure proving the write did not occur moves it to `FAILED_AUTHORITATIVELY`, releases the slot, and permits an explicit retry under the pact's current policy while preserving state history and incrementing attempt count.

`EXPIRED` applies only to a reservation for which execution never began. Stage 1 does not implement time-driven expiry because it has no clock/evidence service; future implementation must prove that no downstream call was issued before releasing authority.

## Consequences

Fail-closed ambiguity can delay legitimate compensation. This is preferable to duplicated value movement and must be surfaced for reconciliation rather than hidden behind automatic retries. Stage 1 proves only in-process behavior; durable recovery requires the later Firestore implementation.
