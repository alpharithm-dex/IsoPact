# ADR-008: Firestore reservation protocol

- Status: Accepted
- Date: 2026-08-23

## Context

Stage 1 proved outcome isolation inside one process. Stage 4 must preserve semantic duplicate and
exclusive resolution authority across unrelated callers and OS processes, while leaving unrelated
pacts independent.

## Decision

Use the official Google Cloud Firestore Python server client and a transaction over one pact's
operation and slot documents. The economic operation identity and the exclusive resolution slot are
separate keys. The repository implements the Stage 1 abstraction, so `ReservationEngine` is unaware
of whether storage is in memory or Firestore.

No process-local mutex participates in the live repository's safety decision. Firestore transaction
commit establishes authority. Repository errors fail closed.

## Consequences

- Independent processes observe durable state and cannot both acquire one semantic operation/slot.
- Contention is scoped to pact/slot documents instead of one global enterprise document.
- Ambiguous outcomes survive restart.
- Firestore availability and latency are on the consequential authorization path.
- This protocol does not claim a measured throughput ceiling from the Stage 4 proof.
- This protocol does not provide atomicity with external SaaS systems.
