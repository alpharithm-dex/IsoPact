# IsoPact Stage 9 completion report

Status: PASS

The machine-readable gate at `artifacts/security/stage9-gate.json` passed all 38 requested criteria plus required-document, wrong-key and four-participant receipt checks (41/41 total). The full Stage 1–8B regression suite passed 107 tests.

## Portable demo

From the project root:

```powershell
.\.venv-win\Scripts\python.exe scripts\verify_settlement_receipt.py artifacts\security\final-settlement-receipt.json
.\.venv-win\Scripts\python.exe scripts\verify_settlement_receipt.py artifacts\security\tampered-receipt.json
```

Expected results are `OVERALL INTEGRITY: VALID` and `OVERALL INTEGRITY: INVALID`, respectively.

## Live signed case

- Pact: `pact_stage8b-e2e-20260824030616_f596af82b579848a30f2`
- Claims: 8, terminal hash `febc6e17ab91fcf169b2fdf0fa71af9099a98f571c0b7ccd674b7205134735f1`
- Checkpoint: `checkpoint_pact_stage8b-e2e-20260824030616_f596af82b579848a30f2_00000008`
- Receipt: `receipt_pact_stage8b-e2e-20260824030616_f596af82b579848a30f2_00000008_all-participants`
- Signing: Cloud KMS `EC_SIGN_P256_SHA256`, version 2, `africa-south1`
- Result: full integrity valid
- Economics derived through Stage 6 reducer: $200 captured, $200 refund, $50 goodwill, $0 replacement, $250 final compensation and $400 projected invalid value protected

## Evidence index

- `artifacts/security/stage9-gate.json`: final gate
- `artifacts/security/final-settlement-receipt.json`: portable signed receipt
- `artifacts/security/live-kms-checkpoint.json`: signed final checkpoint
- `artifacts/security/stateclaims.json`: final ordered claim chain
- `artifacts/security/public-keys.json`: public verification material
- `artifacts/security/full-verification.json`: verifier result
- `artifacts/security/tamper-tests.json`: mutation, deletion, reorder, injection, wrong-key and rollback tests
- `artifacts/security/claim-chain-concurrency.json`: live 25-way Firestore proof
- `artifacts/security/key-rotation.json`: versions 1 and 2 verification
- `artifacts/security/kms-failure.json`: honest receipt-pending behavior
- `artifacts/security/model-armor-proof.json`: live regional screening and failure behavior
- `artifacts/security/forged-evidence-rejection.json`: live Secret Manager/HMAC evidence proof
- `artifacts/security/gateway-auth-attacks.json`: JWT and replay proof
- `artifacts/security/iam-audit.json`: least-privilege and credential audit
- `artifacts/security/performance.json`: separate latency measurements
- `artifacts/agents/stage8b-end-to-end.json`: complete live remote-agent case

## Known risks

- A single pact root is a Firestore contention point: 25 simultaneous appends had p50 3150.627 ms and p95 5190.374 ms.
- The default Compute Engine service account has a pre-existing project Editor grant. It was flagged, not silently revoked.
- Firestore is mutable storage; append-only is enforced by the repository and post-checkpoint mutation is detectable, not physically impossible.
- Model Armor is defense in depth. Deterministic business controls remain authoritative if it misses or is unavailable.

Stage 10 was not started.
