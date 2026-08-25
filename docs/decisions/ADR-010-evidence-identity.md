# ADR-010: Source-authoritative evidence identity

- Status: Accepted
- Date: 2026-08-23

## Context

Pub/Sub can redeliver a message, and a publisher can emit the same logical external event in multiple
messages. Pub/Sub message IDs therefore identify transport envelopes, not business facts.

## Decision

Derive logical Evidence identity from `pact_id`, normalized source system, authoritative
`source_event_id`, evidence type, subject, and external object. Use that deterministic key as the
Firestore Evidence document ID. Persist each transport attempt separately under
`evidence_deliveries` with its Pub/Sub message ID and timestamps.

## Consequences

- One source event creates one logical Evidence record, EconomicEvent, and effective settlement
  transition under concurrency.
- Distinct message IDs do not duplicate value.
- Transport observability is retained instead of discarded by dedupe.
- A source system must provide a stable event ID or a trusted adapter must derive a canonical one.
