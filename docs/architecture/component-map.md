# Component Map

## Runtime flow

```text
request + policy
  -> Pact Compiler (Gemini candidate only)
  -> Deterministic Pact Validator
  -> Pact Graph / Firestore

ADK agents -> IsoPact Gateway -> Invariant + Reservation Engine -> external MCP adapters
                    |                         |                       |
                    +-> StateClaims ----------+<-- async evidence ---+
                                               -> Resolver
                                               -> Compensation Registry
                                               -> Approval service
                                               -> Settlement Receipt
```

## Components and responsibilities

| Component | Responsibility | Deterministic authority | Planned runtime |
|---|---|---|---|
| Pact Compiler | Produce schema-constrained candidate pact from untrusted context | None | Gemini/Vertex AI; fixture locally |
| Pact Validator | Enforce known policies, bounds, subjects, evidence types, and authorities | Activates pact | Python domain service |
| IsoPact Gateway | Intercept, identify, correlate, normalize, decide, reserve, call, and record | Grants downstream execution only after policy and reservation success | FastAPI on Cloud Run |
| Action Normalizer | Map Jira/Stripe/carrier/warehouse/CRM tools to canonical domain actions | Defines semantic event identity | Pure Python |
| Invariant Engine | Evaluate versioned rules and economic position | `ALLOW/BLOCK/DEFER/REQUIRE_APPROVAL`; lifecycle recommendation | Pure Python |
| Reservation Engine | Claim operation key and semantic exclusive slot | Per-pact execution authority | Repository transaction |
| Pact Graph Repository | Persist pacts, claims, events, evidence, conflicts, plans, approvals, receipts | Atomic per-pact mutation and deduplication | Firestore; emulator/in-memory locally |
| Event Ingestor | Validate, deduplicate, append, and trigger re-evaluation | Evidence admission, not business authorization | Pub/Sub consumer |
| Resolver | Explain conflict and propose registered recovery choices | None | Gemini/ADK plus deterministic fixture |
| Compensation Registry/Executor | Resolve typed inverse operation and recheck live preconditions | Compensation authorization subject to policy/approval | Python service through Gateway |
| Approval Service | Capture scoped, expiring human decision as Evidence | Grants only the precise registered action/version described | API/UI plus repository |
| Receipt Service | Build canonical receipt, graph root, signature, verification data | Marks settlement only after deterministic closure check | Python + Cloud KMS |
| Agent Fleet | Support, fulfillment, retention, settlement responsibilities | Limited by identity/tool scopes; all writes traverse Gateway | Google ADK |
| Mock Enterprise Fleet | Deterministic Jira, Stripe, carrier, warehouse, CRM behavior | External state simulation only | Isolated FastAPI/MCP-style services |
| Judge UI | Show request, graph, platform states, economics, decisions, and receipt causality | Read-only | React + TypeScript |
| Observability | Correlate traces, rule decisions, model contributions, events, and latency | None | OpenTelemetry + Cloud Logging/Trace |

## Trust boundaries

| Boundary | Trusted assertions | Untrusted or insufficient assertions | Required control |
|---|---|---|---|
| Agent -> Gateway | Authenticated identity and granted role | Agent-declared completion, amounts, pact link without validation | Identity verification, explicit pact correlation, least-authority tool scope |
| Gateway -> external MCP service | Gateway decision and idempotency metadata | External availability and eventual result | Timeouts, no silent bypass, `UNCERTAIN` state, follow-up evidence |
| External MCP service -> IsoPact | Signed/verified authoritative events per adapter policy | Immediate `accepted`, arbitrary text, replayed webhook | Schema validation, source authentication, event deduplication, evidence ranking |
| Gemini -> deterministic core | Structured candidate and explanation | Any policy override, permission, state transition, operation | Strict schema, allowlists, bounds, policy pinning, separate logs |
| Firestore -> services | Transactionally read stored record | Cross-SaaS atomicity or truth about outside systems | Per-pact transactions, optimistic retries, authoritative evidence references |
| Pub/Sub -> event consumer | Delivery envelope | Exactly-once assumption or ordering assumption | Event IDs, idempotent handlers, ordering-independent reducers |
| Human approver -> executor | Authenticated, scoped approval record | Open-ended approval or stale approval | Scope, version, expiry, audit trail, execution-time recheck |

## Repository structure

```text
apps/
  api/                    # Gateway, pact, evidence, approval and receipt HTTP APIs
  web/                    # React/TypeScript judge interface
  agents/                 # Google ADK agent definitions and runners
services/
  jira_mock/              # Deterministic ticket system
  stripe_mock/            # Accepted/pending and delayed settlement
  carrier_mock/           # Label lifecycle
  warehouse_mock/         # Inventory reservation lifecycle
  crm_mock/               # Goodwill credit lifecycle
src/isopact/
  domain/                 # Entities, value objects, enums, errors
  policies/               # Versioned deterministic invariants
  reservations/           # Operation keys, slots, state machine
  gateway/                # Classification, normalization, interception
  graph/                  # Repository ports and graph reducers
  evidence/               # Ranking, ingestion, deduplication
  compiler/               # Gemini candidate schemas + deterministic validator
  resolver/               # Plan schemas, registry, executor, approvals
  receipts/               # Canonicalization, hashing, signing, verification
  telemetry/              # Trace/log conventions
  adapters/               # Firestore, Pub/Sub, KMS, Vertex AI, external clients
fixtures/
  scenarios/              # Versioned virtual-clock replay inputs
  model/                  # Clearly labeled deterministic model outputs
tests/
  unit/
  integration/
  concurrency/
  adversarial/
  e2e/
scripts/                  # Replays, benchmarks, deployment verification
infra/                    # Google Cloud deployment definitions
docs/
  architecture/
  decisions/
  evidence/
  benchmarks/
```

Dependencies point inward: apps/adapters depend on domain ports; the deterministic domain does not import Google SDKs, web frameworks, Gemini, or mocks.

## MVP requirement coverage

| Proposal requirement | Owning component(s) | Proof stage |
|---|---|---:|
| Commerce domain and explicit case correlation | Domain, Gateway | 1, 4 |
| Support, fulfillment, retention agents | Agent Fleet | 8 |
| Jira/Stripe/shipping/CRM mocks (plus warehouse required by demo) | Mock Enterprise Fleet | 2 |
| Outcome Pact extraction | Compiler + Validator | 3 |
| Persistent Pact Graph | Graph Repository | 5 |
| Async payment/shipment events | Event Ingestor | 2, 5 |
| 5-8 deterministic invariants | Invariant Engine | 6 |
| Duplicate interception and per-pact serialization | Gateway + Reservation Engine | 1, 4 |
| Typed compensation and safe automatic reconciliation | Registry/Executor | 7 |
| Human approval | Approval Service | 7 |
| Hash-linked claims and KMS checkpoint | Receipt/Graph services | 9 |
| Settlement Receipt | Receipt Service | 5, 9 |
| Replay benchmark | Fixtures/scripts/telemetry | 12 |
| Judge-facing live Pact Graph | Web UI | 11 |
| Google Cloud deployment | Cloud adapters/infra | 13 |
