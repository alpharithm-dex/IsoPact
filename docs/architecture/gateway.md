# IsoPact Gateway — Stage 4

## Scope

`IsoPactGatewayInterceptor` is the Stage 4 deterministic safety kernel. It replaces
`AllowAllInterceptor` at the existing Stage 2 `InterceptionPort`; the scenario, virtual clock,
scheduled actions, and simulated external services are unchanged.

The Gateway protects four participating consequential writes:

- `stripe.create_refund` → `successful_refund` → `primary_compensation`
- `carrier.create_label` → `confirmed_replacement` → `primary_compensation`
- `warehouse.reserve_stock` → `confirmed_replacement` → `primary_compensation`
- `crm.issue_credit` → `authorized_goodwill` → `goodwill`

Jira ticket creation and closure remain outside the Stage 4 safety kernel. The protected replay
therefore still closes the ticket after the payment API accepts the refund request. Settlement-aware
ticket closure belongs to the Stage 5 evidence and later invariant work.

## Activation boundary

```text
CandidateOutcomePact (untrusted model output)
  -> deterministic semantic validation
ValidatedOutcomePactDraft (DRAFT_NOT_ENFORCEABLE)
  -> authoritative subjects + exact trusted policy version + deterministic activation
ActiveOutcomePact (enforceable)
```

Activation verifies the validated draft against authoritative order/customer context and the trusted
policy catalog. It derives the pact ID, policy envelope, transaction value, and slot map without a
model call. An active pact is persisted before interception.

## Write lifecycle

1. Normalize caller, target/tool, economic operation, semantic identity, and slot.
2. Run a Firestore transaction that reserves authority.
3. Return non-ALLOW on conflict, duplicate, uncertainty, approval need, or repository failure.
4. After committed ALLOW, transition `RESERVED -> EXECUTING`.
5. Execute the external call outside the transaction callback.
6. Persist the immediate result as `CONFIRMED`, `FAILED_AUTHORITATIVELY`, or `OUTCOME_UNKNOWN`.

Every result carries structured audit fields: pact, actor, action, normalized target/tool, semantic
operation identity, slot, policy ID/version, before/after state, decision, reason, external-call flag,
and trace ID. Natural-language reasoning has no decision authority.

## Fail-closed behavior

If Firestore cannot establish or transition reservation authority, a protected write returns
`DEFER/FIRESTORE_RESERVATION_UNAVAILABLE`; the runner does not call the downstream service. There is
no fallback from the Gateway to `AllowAllInterceptor`.

## Explicit limitations

Stage 4 does not implement settlement evidence, the full Pact Graph, event ingestion, a resolver,
the complete invariant engine, UI, benchmarking, or receipt signing. Firestore and external SaaS
systems do not share a transaction; the design provides durable fail-closed authority, not cross-system
ACID atomicity.
