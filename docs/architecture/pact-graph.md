# Persistent Pact Graph — Stage 5

## Purpose

The Pact Graph answers whether an intended business outcome is evidenced. It does not replace the
Stage 4 Gateway decision about whether a consequential action may execute. Authorization, execution,
API acceptance, pending external state, authoritative success/failure, and settlement remain separate.

The graph is a linked, case-scoped Firestore aggregate, not a universal graph database.

## Firestore layout

```text
pacts/{pact_id}                         Pact aggregate and resolved projection
  participants/{participant_id}         Human, agent, and system participants
  claims/{claim_id}                     Append-oriented StateClaims
  operations/{operation_identity}       Stage 4 reservation reference
  economic_events/{event_id}            Deduplicated economic facts
  evidence/{logical_evidence_id}         Logical trusted evidence
  evidence_deliveries/{delivery_id}      Transport provenance for every delivery
  conflicts/{conflict_id}               Authoritative failure/conflict records
  settlement_evaluations/{evaluation}   Deterministic evaluations by graph revision
  settlement_proofs/{generation}         Non-cryptographic Stage 5 settlement summary
```

The pact root carries its pinned policy, selected resolution, graph revision, lifecycle state,
resolved operation projections, settlement generation, and transition count. All data is scoped by
`pact_id`; there is no global graph or contention document.

## StateClaims

Each replay action produces a claim with its source, actor, subject, external object, operation,
immediate state, explicit evidence rank, logical/event time, ingestion time, trace, and references.
Authoritative events and verified queries also append claims linked to their Evidence record.

Claims are assertions, not settlement authority. A Jira `CLOSED` claim, an agent `COMPLETE` claim,
and an API `PENDING` claim can coexist while the pact remains `PENDING`.

## Resolved state

The root's `resolved_operations` is a deterministic projection of append-oriented evidence. The
reducer compares, in order:

1. operation attempt (newer authoritative attempt wins);
2. evidence rank (lower numeric rank is stronger);
3. finality (`SUCCEEDED`/`FAILED` dominates `PENDING`);
4. source event time for evidence from the same attempt, rank, and finality.

Arrival order is not a truth source. Rank 3 pending data arriving after Rank 1 success cannot regress
the operation. Recency legitimately matters only between equally trusted, equally final observations
for the same attempt.

## Lifecycle

Stage 5 demonstrates `OPEN`, `PENDING`, and `SETTLED`:

- `OPEN`: no selected path, or an authoritative selected-path failure requires new work.
- `PENDING`: an allowed path is selected but required evidence is absent or insufficiently ranked.
- `SETTLED`: trusted policy requirements for the selected path are satisfied once.

`AT_RISK`, `VIOLATED`, and `ESCALATED` remain available vocabulary but are not forced into the narrow
Stage 5 evaluator. The full economic invariant lifecycle belongs to Stage 6.

## Settlement proof

The Stage 5 `SettlementProof` records the pact, selected resolution, status, qualifying evidence IDs,
external state projection, policy ID/version, and settlement time. It is deliberately non-cryptographic
and is not called tamper-evident; signed receipts remain a later stage.
