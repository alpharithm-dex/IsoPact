# Threat Model

## Assets and safety objectives

Protected assets are execution authority, money/inventory/entitlement state, pact policy, approvals, evidence provenance, claim ordering, signing keys, credentials, and judge-facing truth. Primary objectives are: no duplicate or conflicting protected write; no unsupported settlement; no unregistered compensation; no forged/stale approval or evidence; and no false cloud/security claim.

## Threats and controls

| Threat | Consequence | Preventive/detective controls | Fail behavior |
|---|---|---|---|
| Prompt injection in ticket/tool content | Model proposes policy bypass | Treat all text as data; strict structured output; deterministic allowlists, bounds, and policy pinning; Model Armor only if available and verified | Candidate rejected; enforcement remains active |
| Compromised/over-privileged agent | Unauthorized tool or amount | Authenticated participant, least-authority tool scopes, authority limits, Gateway as mandatory write path | `BLOCK` and audit |
| Gateway bypass/direct SaaS write | Pact graph diverges | Network/service-account restrictions in production; reconciliation queries/events; alert on unattributed external changes | Mark `AT_RISK`/`VIOLATED`; never pretend prevention |
| Concurrent duplicate or refund/replacement race | Excess compensation | Semantic keys, shared exclusive slot, Firestore per-pact transaction | One reservation wins; others block/idempotently reuse |
| Crash/timeout after downstream call | Duplicate retry | `UNCERTAIN` reservation, external lookup by idempotency reference, no automatic reissue | `DEFER` until reconciled |
| Replayed/forged webhook | False settlement or duplicate value | Source authentication, schema and subject checks, deterministic event ID, evidence rank | Reject/quarantine; no state advance |
| Out-of-order event | State regression | Monotonic external lifecycle rules, event-time-aware reducer, terminal-state constraints | Preserve prior valid state and flag conflict |
| Stale resolver plan / TOCTOU | Unsafe cancellation | Execution-time query and recheck of registry, preconditions, authority, policy, approval, idempotency | Mark plan `STALE`, escalate |
| Forged, broad, expired approval | Unauthorized consequential action | Authenticated approver, exact action/amount/subject/policy scope, expiry, immutable audit evidence | `REQUIRE_APPROVAL`/`BLOCK` |
| Policy tampering/downgrade | Weakened invariants | Versioned immutable policy artifacts, code review, hashes in decisions/receipts | Fail closed on unknown/missing version |
| Claim deletion/reordering | Misleading audit/receipt | Per-pact sequence transaction, hash chain, checkpoint root, Cloud KMS signature | Verification fails; pact cannot produce valid receipt |
| Secret/key exposure | Connector/signature compromise | Secret Manager, KMS non-exportable keys, redacted structured logs, repository secret scan | Revoke/rotate; do not claim integrity during compromise |
| Tenant/case confusion | Cross-case data/actions | Explicit pact/subject IDs, authorization filters, subject constraints on evidence | Reject ambiguous consequential correlation |
| Firestore/Pub/Sub outage | Lost enforcement/evidence | No bypass, durable retry/dead-letter design, health telemetry | High-risk writes fail closed; cases stay unsettled |
| Gemini outage or malformed output | No interpretation/recovery | Deterministic core independent of model; strict parser; fixture only in dev | Candidate/plan unavailable; no protected write authorized by fallback text |
| Demo manipulation or fabricated metrics | Invalid submission claims | Versioned fixture, machine-readable replay, raw benchmark artifacts, environment provenance | Report limitation; never substitute invented result |

## Trust boundary notes

- Firestore transactions serialize IsoPact records only; they cannot roll back Stripe, Jira, carrier, warehouse, or CRM.
- Pub/Sub is treated as at-least-once and potentially out of order.
- External API success is a claim. Only adapter-specific evidence policy determines whether it is authoritative.
- Human approval is authority for a scoped decision, not proof that an external consequence occurred.
- Memory Bank and conversational memory may add context but never replace the Pact Graph or evidence.

## Security verification contract

Later stages must include: concurrent write tests; prompt-injection tests; forged/replayed/out-of-order event tests; TOCTOU compensation tests; approval scope/expiry tests; hash-chain tamper tests; secret scanning; identity/authorization negative tests; and forced dependency outage tests demonstrating fail-closed behavior.

## Residual risks

External writes can occur outside the Gateway; upstream systems can emit incorrect authoritative data; a privileged cloud administrator can modify infrastructure; Firestore per-document contention limits scale; and compensation cannot make all side effects reversible. These are detected, contained, escalated, and documented rather than represented as cross-system atomicity.
