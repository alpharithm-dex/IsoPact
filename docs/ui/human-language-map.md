# UI-R1 — Human-first language and information architecture audit

Status: **PASS — audit and proposed copy only.** No React components, styles, API contracts, backend state, reason codes, evidence ranks, invariant IDs, economics, receipt verification, or trace data were changed in UI-R1.

## Objective

The first screen must tell a judge: a customer has a $200 problem; multiple agents can take conflicting actions; IsoPact stops the unsafe combination; closing a ticket is not the same as resolving the business problem; and source-system confirmation makes the outcome final. Technical proof remains available after that story, not before it.

## Audit findings

| Surface | Current primary wording | Finding | UI-R2 proposed copy |
|---|---|---|---|
| Header | `PACT STATE`, `OPEN`, `PENDING`, raw pact ID | Lifecycle and identifier arrive before the case meaning. | `CASE STATUS` with human state, e.g. `Waiting for confirmation`; show raw pact ID in System Proof. |
| Scenario navigation | `Protected outcome`, `Pre-existing divergence`, `Stale plan`, `Ambiguous write` | Three labels require internal distributed-systems vocabulary. | `Protected Case`, `Recovery`, `World Changed`, `Lost Response`; retain technical subtitles. |
| Evidence mode | `LIVE MODE`, `VERIFIED REPLAY` | Accurate, but the distinction needs a plain-language explanation. | Keep terms; add `Live data` / `Recorded, verified walkthrough` helper text. |
| Graph title and badge | `LIVE OUTCOME PACT GRAPH`, `OPEN`, `PENDING`, `VIOLATED`, `OUTCOME_UNKNOWN` | The graph is accurate, but starts with internal state names. | `What is happening now` and human state badge; raw lifecycle in expandable case details. |
| Graph legend | `active`, `pending`, `allowed`, `blocked`, `verified`, `settled` | Mostly understandable; `pending` and `settled` need business context. | `In progress`, `Waiting for confirmation`, `Allowed`, `Stopped`, `Confirmed`, `Resolved`. |
| Graph node state/detail | `PACT OPEN`, `Rank 3 only`, `Authority retained`, `World changed` | Node facts mix user story and system internals. | Show a short business statement first; technical state/detail in a secondary line or details panel. |
| Graph edge labels | `Rank 1 evidence`, `Rank 3 only`, `NO CALL` | Rank is not meaningful to a first-time judge. | `Confirmed by the source system`, `Accepted, not yet confirmed`, `No external action taken`; retain rank in details. |
| Economic panel | `OUTCOME / ECONOMIC POSITION`, `ISOPACT PROTECTED`, `Projected invalid value prevented` | Economics are exact but header and final metric are technical. | `Customer outcome` / `Protected Case`; `Conflicting projected value prevented` with the existing `Not a cash-saved claim` note. |
| Business outcome card | `NOT SETTLED`, `Authoritative settlement conditions satisfied` | Both are technically exact but abstract. | `Waiting for confirmation` / `Resolved and verified`; technical lifecycle as a secondary subtitle. |
| Callouts | reason codes such as `EXCLUSIVE_RESOLUTION_CONFLICT`, `DUPLICATE_OPERATION`, `AUTHORITATIVE_SETTLEMENT_EVIDENCE_MISSING` | The reason code is visually co-equal with the verdict. | Plain explanation as verdict/subtitle; raw code behind `Technical details`. |
| Chronicle | `CAUSAL CHRONICLE`, `Backend-derived`, inline `Rank n` | Heading and metadata are engineering-centric. | `What happened, and why`; `Verified from the system`; human evidence phrase inline, raw rank in detail. |
| Reconciliation | `Pre-existing divergence`, `CONSTRAINED RESOLUTION`, `REGISTERED_AUTOMATIC_PLAN_VALID` | The recovery story is obscured by architecture terms. | `Recovery`; `Checking a safe recovery plan`; `Safe to proceed automatically` with technical code in details. |
| World-changed / TOCTOU | `Stale plan`, `TOCTOU PROOF`, `EXECUTION_STATE_INELIGIBLE` | The story is clear only after someone knows TOCTOU. | `World Changed` with subtitle `TOCTOU safety proof`; `The situation changed — action stopped`. |
| Lost-response / unknown | `Ambiguous write`, `OUTCOME UNKNOWN`, `POSSIBLE_PRIOR_EXECUTION` | State name describes implementation ambiguity, not customer impact. | `Lost Response` with subtitle `OUTCOME_UNKNOWN recovery`; `We can't confirm what happened yet`. |
| Receipt | `CRYPTOGRAPHIC OUTCOME PROOF`, `Settlement Receipt`, `Terminal claim hash`, `KMS key version` | The outcome is strong; raw proof fields arrive too early. | `Verified outcome receipt`; show successful outcome and integrity first; move IDs, signatures, KMS, checkpoint, hash to technical details. |
| System Proof | `Operational evidence`, `Gateway latency p95`, `Firestore authorization`, `OTLP / gRPC` | Correct engineering evidence, but not a business-first entry point. | Keep `System Proof`; introduce with `Why this result can be trusted`; group raw service and telemetry fields under `Technical proof`. |
| Replay controls | `Reset replay`, `Step replay`, `1×`, `01 / 10` | Functional but not explanatory. | `Start again`, `Next moment`, `Speed`, `Step 1 of 10`; preserve keyboard/ARIA labels. |
| Loading/error states | `Reading authoritative Pact Graph…`, `No settlement state is inferred…` | Safe and accurate, but jargon-heavy during the first interaction. | `Loading the verified case…` / `We do not guess whether the business problem is resolved.` Keep raw error only under details. |

## Terminology map

| Internal term | Current UI wording | Proposed human-facing wording | Optional technical subtitle | Technical wording remains visible |
|---|---|---|---|---|
| `EXCLUSIVE_RESOLUTION_CONFLICT` | `EXCLUSIVE_RESOLUTION_CONFLICT` | Another resolution is already in progress | Exclusive resolution conflict | Callout technical details and Chronicle detail |
| `DUPLICATE_OPERATION` | `DUPLICATE_OPERATION` | This refund was already requested | Duplicate operation | Callout technical details and Chronicle detail |
| Rank 4 Evidence | `RANK 4 INTERPRETATION` | Agent-reported | Rank 4 evidence | Chronicle and System Proof details |
| Rank 3 | `Rank 3 only` | Request accepted, not yet confirmed | Rank 3 evidence | Chronicle and evidence details |
| Rank 1 | `Rank 1 evidence`, `RANK 1` | Confirmed by the source system | Rank 1 evidence | Chronicle and evidence details |
| `PENDING` | `PENDING` | Waiting for confirmation | Lifecycle: PENDING | Case details, receipt, System Proof |
| `SETTLED` | `SETTLED` | Resolved and verified | Lifecycle: SETTLED | Case details, receipt, System Proof |
| `VIOLATED` | `VIOLATED` | Conflicting actions detected | Lifecycle: VIOLATED | Case details and System Proof |
| `OUTCOME_UNKNOWN` | `OUTCOME UNKNOWN` | We can't confirm what happened yet | OUTCOME_UNKNOWN | Lost Response subtitle and technical details |
| `PRECONDITION_FAILED` | `PRECONDITION FAILED` / `EXECUTION_STATE_INELIGIBLE` | The situation changed — action stopped | Execution precondition failed | World Changed technical details |
| `VALID_AUTOMATIC` | `REGISTERED_AUTOMATIC_PLAN_VALID` | Safe to proceed automatically | Registered automatic plan valid | Recovery technical details |
| Invariant Engine | `Invariant engine` | Business rules check | Invariant Engine | System Proof technical proof |
| Compensation Registry | `2 REGISTERED ACTIONS` / `REGISTERED...` | Approved recovery actions | Compensation Registry | Recovery technical details |
| StateClaim | `StateClaim` | Verified case update | StateClaim | Chronicle drill-down |
| Settlement Receipt | `Settlement Receipt` | Verified outcome receipt | Settlement Receipt | Receipt heading/details |
| Terminal hash | `Terminal hash`, `Terminal claim hash` | Final integrity fingerprint | Terminal hash | Receipt technical details |
| Projected invalid value prevented | `Projected invalid value prevented` | Conflicting projected value prevented | Projected invalid value prevented | Economic note/details; never call it cash saved |
| `AUTHORITATIVE_SETTLEMENT_EVIDENCE_MISSING` | `AUTHORITATIVE_SETTLEMENT_EVIDENCE_MISSING` | We are still waiting for the source system to confirm | Authoritative settlement evidence missing | Callout technical details |
| `POSSIBLE_PRIOR_EXECUTION` | `POSSIBLE_PRIOR_EXECUTION` | We won't retry until we know what happened | Possible prior execution | Lost Response technical details |
| `SIGNATURE_INVALID` | `SIGNATURE_INVALID` | This receipt was changed and cannot be trusted | Signature invalid | Tamper-test technical details |
| KMS key version | `KMS key version` | Signing key version | KMS key version | Receipt technical details |
| Claim chain | `Claim chain` | Recorded update history | Claim chain | Receipt technical details |
| Trace / span / OTLP | `Live trace`, `Cloud Trace`, `OTLP / gRPC` | Technical activity record | Trace / span / OTLP | System Proof technical proof only |

## Language tiers

### Primary

These are visible without opening a drawer or expanding a timeline item. They must use plain business language.

| Element | UI-R2 primary copy |
|---|---|
| Header status | `CASE STATUS` → `Waiting for confirmation`, `Resolved and verified`, `Conflicting actions detected`, or `We can't confirm what happened yet` |
| Main graph | `What is happening now` |
| Graph state | `In progress`, `Waiting for confirmation`, `Resolved and verified`, `Conflicting actions detected` |
| Graph edge | `Confirmed by the source system`, `Accepted, not yet confirmed`, `No external action taken` |
| Economic panel | `Customer outcome` |
| Protection label | `Protected Case` |
| Block card | `IsoPact stopped this action` plus the human reason |
| Outcome card | `What happens next` with the human outcome state |
| Chronicle | `What happened, and why` |
| Receipt entry point | `Verified outcome receipt` |
| Loading | `Loading the verified case…` |
| Error | `Live view is unavailable` and `Open verified walkthrough` |

### Secondary

Secondary surfaces pair plain language with the technical term in smaller type or an expandable section.

| Element | UI-R2 secondary copy |
|---|---|
| Scenario subtitles | `TOCTOU safety proof`, `OUTCOME_UNKNOWN recovery`, `Verified recorded walkthrough` |
| Lifecycle | `Waiting for confirmation` — `PENDING` |
| Evidence | `Confirmed by the source system` — `Rank 1` |
| Recovery | `Safe to proceed automatically` — `VALID_AUTOMATIC` |
| Receipt integrity | `Recorded update history is intact` — `Claim chain valid` |
| System proof | `Why this result can be trusted` → `Technical proof` |
| Node details | `Request accepted, not yet confirmed` — `Rank 3` |

### Engineering-only

Keep these intact, but behind `Technical details`, expanded Chronicle entries, Receipt technical details, or System Proof technical proof. They must not dominate the first screen.

- Raw reason codes, lifecycle constants, invariant IDs, policy/rule versions
- Evidence IDs, ranks, source sequence, operation identity
- Pact IDs, trace IDs, span classes, StateClaim sequence and claim hashes
- Receipt/checkpoint IDs, signature algorithm, signing key resource and version
- Cloud Run/Gateway, Firestore, Pub/Sub, KMS, OpenTelemetry, OTLP/gRPC details

## Navigation proposal

| Current label | Proposed label | Technical subtitle |
|---|---|---|
| Protected outcome | Protected Case | Live case |
| Without IsoPact | Without IsoPact | Verified recorded walkthrough |
| Pre-existing divergence | Recovery | Resolve actions already in conflict |
| Stale plan | World Changed | TOCTOU safety proof |
| Ambiguous write | Lost Response | OUTCOME_UNKNOWN recovery |
| System Proof | System Proof | Why this result can be trusted |

## Ten-second judge comprehension test

The proposed first viewport provides this sequence, without requiring a definition of TOCTOU, KMS, evidence ranks, StateClaims, invariants, semantic idempotency, or provenance:

1. `Missing order — $200` establishes the customer problem.
2. The graph names Support, Fulfillment, and Retention as the agents acting on it.
3. `Another resolution is already in progress` makes the conflict visible.
4. `IsoPact stopped this action` explains the system response.
5. `A closed ticket is not a settled outcome` and `Waiting for confirmation` separate agent completion from business resolution.
6. `Confirmed by the source system` followed by `Resolved and verified` explains settlement.

The exact economics remain $200 original value, $650 unmanaged projected compensation, $450 projected excess exposure, $250 final authorized compensation, and $400 conflicting projected value prevented. The last phrase remains explicitly qualified as **not** a cash-saved claim.

## Safety and evidence preservation

- Human language changes presentation only; lifecycle semantics, reason codes, evidence ranks, invariant behavior, authority boundaries, API data, and receipt verification stay unchanged.
- `OUTCOME_UNKNOWN` must never be presented as resolved; its human label explicitly preserves uncertainty.
- `VIOLATED` must not be softened into a benign warning; `Conflicting actions detected` retains the severity.
- `VALID_AUTOMATIC` must describe only a validated registered plan, never model authority.
- Receipt technical identifiers, signatures, hashes, and traces remain available for judge drill-down.
- No copy may say `cash saved`, imply cross-SaaS ACID, universal exactly-once behavior, or claim third-party integrations where none are implemented.

## UI-R2 implementation boundary

UI-R2 may introduce display-only mapping functions and progressive disclosure in the React UI. It must not alter backend state names, API contracts, reason codes, evidence ranks internally, invariant IDs, lifecycle semantics, economics, receipt verification, trace metadata, or authorization behavior.
