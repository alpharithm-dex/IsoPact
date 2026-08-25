# Deterministic invariant engine

Stage 6 evaluates the normalized current facts of one Pact Graph with an immutable `RuleSet`. The engine is pure: it performs no external calls and its `model_calls` counter remains zero. Gemini output cannot authorize money, select rule truth, perform arithmetic, qualify evidence, or settle a pact.

The pinned set `commerce_missing_order_rules@1` contains nine rules, each at `1.0.0`: refund bound, exclusive primary resolution, duplicate semantic compensation, settlement evidence, cumulative goodwill, pending-primary conflict, correction reversibility eligibility, currency consistency, and settled-primary immutability. Results retain rule/version, facts, evidence, operation identities, amounts, reason code, explanation, severity, and permitted response classes. `UNKNOWN` is distinct from `PASS`.

Evaluation recomputes all rules per pact. The canonical reducer first collapses history by economic object and source version; rule impacts never replace or get summed into canonical exposure. Firestore stores snapshot-scoped evaluations, economic snapshots, deduplicated protection events, and historical conflicts in one transaction. External systems are never called inside it.

## Lifecycle synthesis

- A hard failure with an already executed active effect is `VIOLATED`.
- A hard failure confined to proposed or blocked work is `AT_RISK`.
- Outstanding approval or a non-reversible automatic-compensation warning is `ESCALATED`.
- Unknown settlement truth while work is pending is `PENDING`.
- `SETTLED` requires the selected resolution, qualified evidence, no open hard conflict, and no approval requirement.
- Otherwise the pact is `OPEN`.

Re-evaluation can resolve an open conflict but never deletes its record. Stage 6 only reports registered compensation eligibility; it does not execute compensation.
