# Evidence pipeline — Stage 5

## Flow

```text
external system
  -> Google Cloud Pub/Sub
  -> deterministic EvidencePipeline
  -> per-pact Firestore transaction
  -> monotonic reducer
  -> settlement evaluator
```

The live resources are:

- topic: `projects/isopact-agentic-20260823/topics/isopact-stage5-evidence`
- pull subscription: `projects/isopact-agentic-20260823/subscriptions/isopact-stage5-evidence-proof`
- exactly-once delivery: disabled

## Explicit evidence hierarchy

1. authoritative settled system-of-record event;
2. authenticated system-of-record query;
3. accepted or pending API response;
4. agent interpretation;
5. unverified natural-language assertion.

Rank is assigned from trusted adapter/type mappings, never by wording. Text saying “Stripe confirmed
the refund” remains Rank 4 or 5 when it came from an agent, ticket, or customer.

The trusted policy maps `successful_refund` to `stripe.refund.succeeded` and permits maximum rank 2.
It maps `confirmed_replacement` to `carrier.shipment.accepted` and requires Rank 1. The model cannot
change either mapping.

## Identity and provenance

Logical evidence identity hashes the pact, normalized source system, authoritative `source_event_id`,
evidence type, subject, and external object. Pub/Sub message ID is transport identity only. Multiple
message IDs for the same source event create one Evidence, while separate `evidence_deliveries`
records preserve all message IDs, publish/receive times, attributes, and mechanisms.

## Transaction and acknowledgment

For a new logical event, one Firestore transaction reads the pact, evidence key, delivery key, and
related reservation before it writes. It atomically creates/deduplicates Evidence, records transport
provenance, appends a StateClaim, adds any EconomicEvent/Conflict, updates the resolved projection,
persists the SettlementEvaluation, reconciles an uncertain reservation where applicable, and creates
at most one settlement transition/proof.

The subscriber acknowledges only after this transaction commits. A failure before durable commit is
not acknowledged and is eligible for redelivery. Firestore aborts are retried with the same business
and delivery identities. No external SaaS action occurs in the graph transaction.

## Query evidence

`StripeQueryEvidenceProvider` represents an authenticated read of simulated payment-system state. It
emits Rank 2 Evidence. A Rank 2 successful refund settles only when the pinned trusted policy permits
Rank 2; the same evidence remains insufficient under a strict Rank 1 requirement.

## Failure and uncertainty

`stripe.refund.failed` creates Rank 1 failure evidence, a failed EconomicEvent, and an open Conflict;
the pact does not settle. `stripe.refund.succeeded` linked to a Stage 4 `OUTCOME_UNKNOWN` operation can
atomically move that reservation to `CONFIRMED`, settle the narrow outcome, and preserve duplicate
blocking without issuing another refund.

This is application-level evidence consistency. Firestore, Pub/Sub, and external SaaS systems do not
participate in one ACID transaction.
