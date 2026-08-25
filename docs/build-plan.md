# IsoPact Dependency-Ordered Build Plan

## Stage gates

Each stage is independently verified and stops with `STATUS: PASS|BLOCKED` and `NEXT STAGE READY: YES|NO`. A later stage must not compensate for a failed earlier guarantee.

| Stage | Deliverable | Depends on | Objective verification checkpoint |
|---:|---|---|---|
| 0 | Architecture contract (this document set) | Proposal | MVP mapping complete; deterministic authorization boundary; repeatable schedule; concurrency/idempotency model; local/cloud split; no cross-SaaS ACID claim |
| 1 | Minimal outcome-isolation domain proof | 0 | Real concurrent tests: one exclusive winner, zero duplicate execution authority, retry idempotency, independent pacts, zero Gemini calls |
| 2 | Deterministic enterprise simulator | 1 | Repeated canonical replay equality; Jira closed/Stripe pending; derived `$650/$450`; inspectable mock states |
| 3 | Gemini candidate pact compiler | 2 | Strict schema; deterministic validation; adversarial injection rejection; fixture/live provenance separated |
| 4 | MCP Gateway + Firestore reservations | 1-3 | 25-way concurrency/torture tests; downstream counts; semantic rather than request-ID dedupe; failure fails closed |
| 5 | Persistent graph and async evidence | 4 | Pending cannot settle; duplicate/out-of-order/failure/success event tests; restart persistence |
| 6 | Versioned invariants and economic engine | 5 | Rule traces; boundary/partial refund tests; separated settled/pending/projected/blocked/recovered/protected values |
| 7 | Resolver, registry, and approval | 6 | Unregistered compensation rejected; TOCTOU refusal; one safe auto compensation; one audited approval case |
| 8 | Real ADK agent fleet | 4-7 | Three distinct agents perform meaningful work through Gateway; async pact survives; memory cannot override evidence; availability claims verified |
| 9 | Security and tamper evidence | 5-8 | Identity/authorization negatives; secret scan; hash tamper detection; KMS verification; outage behavior; only available controls claimed |
| 10 | Observability and causality | 4-9 | One trace follows call -> decision -> tool -> evidence -> re-evaluation; p50/p95 instrumentation; no sensitive payload leakage |
| 11 | Judge-facing Pact Graph UI | 2, 5-10 | Before/after replay displays causal graph, platform states, economics, decisions, evidence rank, and verifiable receipt |
| 12 | Benchmark/adversarial/failure injection | 1-11 | 50 fixed cases; published raw artifacts and measured metrics; concurrent and outage tests; no unsupported percentages |
| 13 | Google Cloud production deployment | 4-12 | Clean deployment; real Cloud Run/Firestore/Pub/Sub/Vertex/KMS/Secret/telemetry evidence; protected replay passes in cloud |
| 14 | Hostile judge review and submission hardening | 0-13 | Clean-clone reproducibility, tests/benchmark/replays, secret scan, architecture-to-runtime consistency, independently verifiable receipt |

## Cross-stage dependency rules

1. The domain model, clock, repository contracts, operation canonicalization, and reservation state machine are established before network services.
2. The baseline simulator reuses the same normalized economic event types as the protected path, preventing display-only totals.
3. Model integrations depend on strict candidate schemas and deterministic validators; the core never imports or calls Gemini.
4. Gateway execution depends on proven reservation behavior; evidence processing depends on stable operation and event identities.
5. Invariants consume the persisted graph; resolver plans consume invariant conflicts but cannot alter policies.
6. Agents and UI integrate only after the protected path is testable without them.
7. Security, observability, benchmarks, and cloud claims attach to actual implemented paths, not planned architecture.

## Verification layers

```text
unit: pure entities, canonicalization, rules, reducers
contract: in-memory and Firestore repositories; every enterprise adapter
concurrency: simultaneous threads/processes against real repository implementation
integration: Gateway + mocks + event bus + persistence
adversarial: injections, malformed evidence, forged identity/approval, stale plans
end-to-end: baseline/protected virtual-clock replay and receipt verification
cloud smoke: deployed protected replay with service-specific evidence
benchmark: fixed corpus, raw per-case outcomes, reproducible aggregate script
```

Every evidence document records commit identifier, environment/mode, exact command, exit code, raw artifact path/hash, and limitations. Fixture, emulator, mock, and live-cloud results must never be conflated.

## Immediate next-stage entry criteria

Stage 1 may begin only after this contract is reviewed and accepted. It must implement only the domain entities needed for reservations, deterministic operation keys, invariant decision interface, in-memory repository, and Firestore repository port—no UI, agents, Gemini, or SaaS mocks.

## Known architectural risks to carry forward

- Canonical semantic identity may produce false equivalence or miss duplicates; golden/adversarial fixtures are mandatory.
- Firestore contention and transaction retry behavior require emulator and live-cloud measurement.
- Ambiguous post-call failure can delay legitimate work; `UNCERTAIN` reconciliation must be explicit.
- Mock authoritative evidence is not proof of a production connector's semantics.
- Availability of newer Google enterprise agent services must be checked before Stage 8/9 and omissions disclosed.
- The proposal's protected narrative both blocks replacement and later cancels it; the demo contract resolves this with a clearly labeled pre-existing-divergence reconciliation variant.
