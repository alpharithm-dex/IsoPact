# ADR-002: Application-Level Outcome Isolation

- Status: Accepted for implementation contract
- Date: 2026-08-23

## Context

Independent authorized agents can create duplicate or mutually incompatible outcomes across systems that cannot participate in one transaction. API acceptance is often asynchronous and cannot establish business settlement.

## Decision

Use application-level outcome isolation per Pact:

1. Normalize each consequential request to a domain action.
2. Derive a semantic economic operation key from pact, resolution path, event type, subject, and normalized value/resource. Pin policy version on the authorization attempt, but exclude it from economic identity so policy publication cannot bypass an existing reservation.
3. Map mutually exclusive resolution paths to shared semantic slots such as `primary_compensation`.
4. In one Firestore transaction anchored on the pact, reserve the operation key and all required slots before the downstream call.
5. Never hold the datastore transaction across the external call.
6. Record immediate external responses as claims; use `UNCERTAIN` after ambiguous failures and reconcile before retrying.
7. Confirm, fail, release, or reverse reservations only under explicit state-machine rules backed by evidence.
8. Require ranked authoritative evidence plus passing invariants before settlement.
9. Reconcile external divergence only through typed, policy-approved compensation with execution-time precondition checks.

## Guarantees

- At most one live authority holder for an exclusive per-pact slot.
- Equivalent retries converge on one semantic reservation even with different request IDs.
- Different pacts do not serialize on a global lock.
- Deterministic enforcement remains available without Gemini.

## Non-guarantees

- No ACID transaction, atomic visibility, rollback, or exactly-once delivery across SaaS systems.
- No prevention of writes that bypass the Gateway.
- No automatic reversal of irreversible or already-settled external effects.
- No universal ordering across pacts.

## Consequences

Unknown outcomes can delay legitimate work, so policies need bounded leases, system-of-record reconciliation, approval, and explicit escalation. Semantic canonicalization becomes security-critical and requires adversarial and cross-language fixtures. The approach is defensible only when downstream call counts and real concurrent tests prove the stated guarantees.
