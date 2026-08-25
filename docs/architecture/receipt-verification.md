# Settlement Receipt verification

A Settlement Receipt is a portable integrity statement for an already-determined settlement. It includes subjects, requested and selected outcomes, lifecycle, authoritative external states, Stage 6 economic position, evidence, participants, reconciliation/approval/exception references, policy/rule versions and final checkpoint binding. It excludes credentials and sensitive source payloads.

Cloud KMS signs canonical receipt and checkpoint bodies with `EC_SIGN_P256_SHA256`. The exact CryptoKeyVersion is embedded. Independent verification hashes the canonical body with SHA-256 and verifies ECDSA P-256 with the retrieved public key; no private key leaves KMS.

Signature-only mode verifies the receipt artifact. Full mode additionally verifies the checkpoint signature, ordered per-pact claim chain, terminal hash/count, receipt-to-checkpoint binding, and evidence-reference subset. It needs local JSON artifacts and public keys only—no Gemini, Agent Runtime, Resolver, Gateway or Firestore write access.

```powershell
python scripts/verify_settlement_receipt.py artifacts/security/final-settlement-receipt.json
python scripts/verify_settlement_receipt.py artifacts/security/tampered-receipt.json
python scripts/verify_settlement_receipt.py artifacts/security/final-settlement-receipt.json --signature-only
```

Success prints `OVERALL INTEGRITY: VALID` and exits 0; failure prints `INVALID`, includes reason codes and exits 1. Verification proves the supplied receipt/history was not changed after signing. It does not query Stripe or prove Stripe's original assertion; authenticated evidence adapters establish source authenticity.

Rotation creates a new enabled CryptoKeyVersion for new receipts while retaining public verification material for historic versions. Verifiers select the embedded exact version. Disabling signing on an old version need not invalidate its public verification. Destruction would impair historic verification and therefore requires retention-policy approval.

If KMS signing fails, deterministic settlement remains `SETTLED`, but issuance is `SETTLED_RECEIPT_PENDING` with no signature. No artifact is represented as signed until KMS succeeds.
