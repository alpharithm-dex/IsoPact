# ADR-014: Authoritative state transitions

## Status

Accepted for Stage 6.

## Decision

Evidence trust rank remains primary. Within the same operation attempt and Rank 1 source object, a changed state requires a strictly newer source sequence and a source-specific valid transition. Stripe refund transitions are `PENDING → SUCCEEDED|FAILED` and `SUCCEEDED → REVERSED`; `FAILED` and `REVERSED` are terminal in the current simulator. Same-state duplicates may advance sequence/time without changing truth.

An older sequence, missing sequence for a correction, or impossible transition cannot overwrite current truth. Rank 3 pending evidence cannot regress Rank 1 success. A stale Rank 1 failure cannot regress success, while a newer legitimate reversal can.

## Consequences

“First Rank 1 wins” and unvalidated “last event wins” are both rejected. New sources require an explicit state machine before same-rank corrections are accepted.
