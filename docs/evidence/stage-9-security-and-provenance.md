# Stage 9 security and provenance evidence

Stage 9 preserves Stage 1–8B semantics and adds canonical StateClaims, per-pact hash chains, signed checkpoints and receipts, authenticated source evidence, hardened agent tokens, minimized audit payloads and model-facing screening.

## Live proofs

- The 25-worker Firestore proof committed contiguous sequences 1–25 with zero forks and a valid terminal hash. Repository semantic mutation was refused.
- The final replay pact `pact_stage8b-e2e-20260824030616_f596af82b579848a30f2` has eight valid linked claims: refund ALLOW/API response, replacement BLOCK, goodwill ALLOW/API response, duplicate refund BLOCK, Rank 4 agent assertion and authenticated Rank 1 Stripe success.
- Cloud KMS key versions 1 and 2 use `EC_SIGN_P256_SHA256` in `africa-south1`. Version 2 signed the final checkpoint and receipt; local public-key verification passed. Version 1 artifacts remain valid.
- Full verification passed. Edited, deleted, reordered and injected claims; a modified receipt; wrong key; and stale checkpoint substitution all failed.
- Injected KMS unavailability left the pact settled, emitted no false signature and produced `SETTLED_RECEIPT_PENDING` issuance metadata.
- Agent JWT attack tests denied expired, future-`nbf`, wrong audience/issuer, unknown SPIFFE subject, unsigned and modified tokens before external calls. Live body identity spoofing was ignored and duplicate replay executed no second refund.
- The live receipt derives its economic position through the Stage 6 `EconomicReducer`: captured 20,000, settled refund 20,000, goodwill 5,000, replacement committed 0, total compensation 25,000 and protected value 40,000 USD minor units.

Artifacts under `artifacts/security` are machine-readable. Run `scripts/verify_settlement_receipt.py` against the final or tampered receipt for the portable demo.

## Honest limitations and audit findings

Cryptographic verification does not re-query external systems or prove their original truth. Firestore append-only behavior is enforced by the repository and detectable after checkpointing, not by an immutable storage service. Per-pact root transactions create measurable contention at 25 simultaneous appends. The existing default Compute Engine service account retains project Editor and is flagged; it was not changed because it predates Stage 9 and may support user workloads. Human owner/admin access was not silently revoked.

The Model Armor API advertised `europe-west1`, not `africa-south1`. Template access is recorded from the live project; deterministic controls fail safely and remain authoritative regardless of screening availability or result.
