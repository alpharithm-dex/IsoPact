# Stage 7 safe reconciliation evidence

Stage 7 passed against live Vertex AI and Firestore project `isopact-agentic-20260823`.

Five live `gemini-3.5-flash` calls returned strict plans. All five were schema-valid, used only supplied registry IDs, and selected both required actions: carrier cancellation followed by warehouse release. Latencies were 10,294; 8,727; 13,255; 8,474; and 10,561 ms. Model prose was not required to match.

The live pre-existing-divergence proof began `VIOLATED` with a $200 recovery candidate and $0 recovered. Deterministic validation returned `VALID_AUTOMATIC`. Carrier `SHIP-001` was rechecked as `CREATED` and cancelled once; warehouse `STK-001` was rechecked as `RESERVED` and released once. Rank-1-style trusted recovery documents for `CANCELLED` and `RELEASED` gated one deduplicated `$200 AUTHORIZED_VALUE_RECOVERED` event. Conflict history remained with status `RESOLVED`; the pending refund left the pact `PENDING`. Later refund success moved it to `SETTLED`.

The same live pact stored ResolutionPlans, CompensationExecutions, a scoped ApprovalRequest and ApprovalDecision, evidence references, invariant snapshots, conflict update, and ProtectionEvent. The live CRM proof made zero calls before approval and one after explicit approval and a fresh precondition check.

Local deterministic proofs show: `CREATED → ACCEPTED` TOCTOU refusal with zero cancellation calls; ambiguous cancellation with one external execution, `OUTCOME_UNKNOWN`, deferred restart retry, and evidence-driven confirmation; rejected and stale approvals with zero unsafe calls; no Stripe reversal; and partial carrier-success/warehouse-failure with $0 recovered. Deterministic validation and execution authorization used zero model calls.

Artifacts are under `artifacts/resolver/`. Performance timings separate Gemini latency, deterministic validation, and precondition reads and are not production scale claims.
