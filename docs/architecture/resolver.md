# Constrained Resolver

Stage 7 separates model judgment from execution authority. A bounded `ResolverContext` contains the pinned outcome, selected resolution, open deterministic conflicts, canonical economic position, reversible source states, evidence summaries, and only the relevant trusted registry candidates. Enterprise text is explicitly untrusted.

Gemini returns a strict `CandidateResolutionPlan` containing registry IDs, preferences, and explanation only. The schema has `extra=forbid`; amounts, targets, payloads, preconditions, authority tiers, tools, and approval overrides are not representable. The deterministic validator binds targets from the Pact Graph, verifies conflict freshness, registry/version, forward-action compatibility, ownership, policy, authority, approval representation, eligibility, and plan consistency. Its model-call count is zero.

Registry policy fixes carrier cancellation before warehouse release. A valid plan is not durable execution authority: immediately before every action, the executor obtains current state from the target system. It reserves semantic authority and commits `EXECUTING` before making the external call. Firestore transaction callbacks contain no external calls.

Resolver failure leaves conflicts and Stages 4–6 enforcement intact. It causes no compensation. Reconciliation removes divergence but cannot establish refund settlement: the primary sequence is `VIOLATED → PENDING`; only later authoritative refund success produces `SETTLED`.
