# IsoPact System Contract

## Purpose and scope

IsoPact is a case-scoped outcome-integrity layer for consequential autonomous work. Its unit of consistency is an Outcome Pact, not a tool call or a universal enterprise data model. The MVP supports only the commerce compensation domain and the `$200` missing-order demonstration.

IsoPact guarantees application-level outcome isolation: before protected writes, deterministic code serializes equivalent and mutually exclusive operations per pact; after external divergence, evidence-ranked reconciliation drives the case to a permitted result. It does **not** provide or claim ACID transactions, two-phase commit, atomic rollback, or a globally consistent transaction across external SaaS systems.

## Normative guarantees

1. Agent completion, workflow completion, API acceptance, and business settlement are distinct states.
2. No value-changing or operationally consequential action is authorized solely by Gemini output.
3. Every protected write is normalized, policy-evaluated, and atomically reserved before downstream execution.
4. Equivalent semantic operations share an operation key; mutually exclusive resolution paths share a reservation slot.
5. Unknown, unavailable, or ambiguous high-risk state fails closed or requires approval according to versioned policy.
6. A pact settles only when deterministic invariants pass and required authoritative evidence is present.
7. Retries and duplicate external events are idempotent.
8. Compensation is limited to the typed Compensation Registry and revalidated immediately before execution.
9. Every decision records inputs, policy/rule versions, evidence references, actor, trace, and explanation.
10. Demonstrated failures and timings come from deterministic fixtures, never stochastic model behavior.

## Lifecycle

| State | Entry condition | Allowed exit |
|---|---|---|
| `OPEN` | Validated pact exists and work remains | `PENDING`, `AT_RISK`, `VIOLATED`, `ESCALATED`, `SETTLED` |
| `PENDING` | An allowed path is in flight or awaits evidence | `OPEN`, `AT_RISK`, `VIOLATED`, `ESCALATED`, `SETTLED` |
| `AT_RISK` | A proposed/pending action would conflict if completed | `PENDING`, `VIOLATED`, `ESCALATED`, `SETTLED` |
| `VIOLATED` | Current evidenced/projected state violates an invariant | `PENDING`, `ESCALATED`, `SETTLED` |
| `ESCALATED` | Policy requires human authority or no safe automatic plan exists | `PENDING`, `VIOLATED`, `SETTLED` |
| `SETTLED` | One permitted outcome has sufficient evidence and all closure invariants pass | Terminal except a new, explicitly linked escalation/correction case |

State transitions are computed from graph state by deterministic code. Gemini may explain a transition or propose a recovery plan but cannot set lifecycle state.

## State and evidence semantics

| Term | Meaning | Settlement authority |
|---|---|---|
| Tool response | Immediate downstream return, such as `accepted` | None unless the response is itself a policy-recognized authoritative final result |
| Agent interpretation | An agent's conclusion about what occurred | None |
| Pending external state | An accepted action whose final effect is unknown | Keeps the pact `PENDING`; cannot settle |
| Authoritative external evidence | Deduplicated webhook or verified system-of-record query meeting the pact's evidence requirement | May satisfy a completion predicate |
| Settlement | Deterministic conclusion that a permitted resolution is evidenced and every required invariant passes | Produces a signed/verifiable Settlement Receipt |

Evidence rank, strongest first: authoritative settled event; verified system-of-record query; accepted/pending response; agent interpretation; unverified natural-language assertion. A weaker rank never satisfies a stronger evidence requirement.

## Decision boundary

Gemini may:

- extract a candidate pact from request, ticket context, and policy references;
- classify ambiguity and propose correlations when explicit identifiers are missing;
- summarize conflicts and evidence;
- rank policy-registered recovery options and explain a proposed plan.

Deterministic code exclusively:

- validates schemas, identifiers, policy references, amounts, authority, and evidence types;
- normalizes tool calls to canonical events;
- generates operation keys and chooses exclusive slots;
- evaluates invariants and economic position;
- atomically grants or denies execution reservations;
- checks compensation registration, preconditions, approval, and idempotency;
- derives lifecycle state and issues Settlement Receipts.

Model failure must leave reservations, invariant enforcement, and fail-closed behavior operational. A deterministic development fixture may replace live Gemini for repeatability, but artifacts must label it as a fixture.

## Gateway execution contract

For every MCP-style call:

1. Establish participant identity and trace context.
2. Resolve the pact using explicit case metadata; do not guess for a consequential write.
3. Classify read/write and normalize the action.
4. Load the pinned pact policy version and current graph snapshot.
5. Evaluate preconditions and invariants.
6. In one per-pact repository transaction, claim the semantic operation key and any exclusive slot.
7. Return `ALLOW`, `BLOCK`, `DEFER`, or `REQUIRE_APPROVAL` with deterministic reasons.
8. Call the downstream adapter only for `ALLOW`.
9. Record the response as a StateClaim, not as settlement by default.
10. Re-evaluate when authoritative evidence arrives; finalize or transition the reservation accordingly.

If execution outcome is unknown after reservation, the reservation becomes `UNCERTAIN`; retries query/reconcile the same semantic operation rather than issuing another write. A confirmed failure may release a slot only under explicit policy and evidence.

## Local and production modes

| Concern | Local deterministic mode | Google Cloud production mode |
|---|---|---|
| Runtime | FastAPI processes | Cloud Run services |
| Store/reservations | In-memory repository for unit tests; Firestore emulator for persistence/concurrency integration tests | Firestore transactions |
| Events | Deterministic virtual-clock event queue; Pub/Sub emulator where useful | Pub/Sub, with Cloud Tasks for deferred rechecks where justified |
| Enterprise systems | Isolated deterministic MCP-style adapters | Real connectors only when configured; mock adapters remain for demo baseline |
| Model | Recorded deterministic compiler/resolver fixture | Gemini through supported Vertex AI SDK; Google ADK for agent fleet |
| Secrets/signing | Test keys clearly labeled non-production | Secret Manager and Cloud KMS |
| Telemetry | Local OpenTelemetry/structured logs | OpenTelemetry exported to Cloud Logging/Trace |

No production integration or Google service is claimed until deployed and evidenced.

## Acceptance boundary

The architecture is valid only if tests later prove: zero duplicate consequential executions; one winner for each exclusive resolution slot; retries remain idempotent; unrelated pacts progress independently; pending acceptance cannot settle; compensation cannot escape the registry; and the final receipt can be independently verified.
