# Human approval boundary

`ApprovalRequest` and `ApprovalDecision` are persistent typed records. The approval identity binds pact, plan, execution, registry action/version, exact target, and policy version. Actor, decision, timestamp, and reason are retained.

Approval changes authority from waiting to eligible; it does not execute an action and cannot alter registry rules. Rejected, expired, missing, or scope-mismatched approvals produce zero external calls. Immediately before an approved action, the executor re-fetches authoritative state. An approved CRM reversal therefore still fails closed if `CR-001` changed from unused/issued to `USED`.

No cryptographic signature is claimed in Stage 7. Identity provenance is recorded; signing remains reserved for later hardening.
