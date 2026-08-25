# ADR-011: Deterministic evidence ranking and monotonic reduction

- Status: Accepted
- Date: 2026-08-23

## Context

API acceptance, ticket text, agent conclusions, verified queries, and authoritative system events
carry different trust. Arrival order can invert, so last-event-wins can regress known truth.

## Decision

Use an explicit five-rank enum, with Rank 1 strongest. Trusted adapters assign rank; text content does
not. Settlement compares evidence against the pinned policy's event type and maximum acceptable rank.

Resolve an operation by attempt, trust rank, finality, then source time. A weaker or older event cannot
replace a stronger projection. Source time is a tiebreaker only for the same attempt/rank/finality.

## Consequences

- Rank 3 pending, Jira closure, Rank 4 agent completion, and Rank 5 prose cannot satisfy Rank 1/2
  refund evidence requirements.
- Rank 2 verified query behavior is policy-controlled.
- Success-before-pending remains success.
- Older-attempt failure cannot overwrite a newer-attempt success.
- Conflicting equally authoritative corrections require explicit source-time semantics and may need a
  richer Stage 6 conflict rule.
