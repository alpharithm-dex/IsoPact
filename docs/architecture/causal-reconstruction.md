# Causal reconstruction

`CaseChronicle` is a read-only derived view over existing Pact Graph claims, Gateway decisions, evidence, conflicts, compensation executions, settlement facts, and receipt references. It persists no events and is not a second source of truth. Four Chronicles cover the primary, reconciliation, TOCTOU, and OUTCOME_UNKNOWN cases.

Business IDs locate authoritative facts; trace/span IDs locate transient observations. Chronicle entries preserve available `caused_by`, `blocked_by`, `confirmed_by`, `reconciled_by`, `invalidated_by`, and `signed_by` references, including operation identities, evidence IDs, claim sequence/hash, rules, conflicts, compensation executions, and receipts.

Synchronous Runtime-to-Gateway calls propagate real W3C context. The live propagation artifact proves an ADK invocation ancestor and Gateway descendants on trace `7cf150602994fa1029fc855b953d380e`. Asynchronous source and consumer executions remain separate traces joined by an OpenTelemetry span link plus stable business references. The live Pub/Sub proof used source event `evt-stage8b-20260824205251`: root consumer `c4a56fb4414a39ab660cf3fd62d551be/23fd15b95078a9fc` links to publisher `7dc674d4131e6f07a1833fdc5486c999/a7acd0076ee992ce`; link attributes carry the pact and source-event IDs. The IDs reconcile to the corresponding Cloud Trace roots, and the completion log follows processing and ACK. Shared business IDs alone are not treated as proof.

Gemini may reason in Compiler and Resolver spans. The dependency assertion finds zero model descendants inside Gateway authorization, reservations, evidence authority, invariant evaluation, deterministic validation, compensation authorization, settlement, or receipt verification.
