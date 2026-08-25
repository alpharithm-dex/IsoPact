# ADR-027: Authenticate authoritative evidence before ranking

Status: Accepted

Verify Stripe-shaped HMAC and timestamp freshness over raw bytes before payload parsing or EvidencePipeline invocation. Load the live key through Secret Manager using a dedicated evidence identity. Only a verified event matching the trusted source/type map may become Rank 1.

Missing, invalid, stale and source-mismatched signatures are rejected with no evidence or settlement transition. HMAC authenticates possession of the shared secret; it does not authorize refunds or replace deterministic settlement evaluation.
