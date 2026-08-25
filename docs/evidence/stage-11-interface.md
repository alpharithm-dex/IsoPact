# Stage 11 interface evidence

## Live case

- Gateway: `https://isopact-outcome-gateway-442539309409.africa-south1.run.app`
- Pact: `pact_stage8b-e2e-20260824205251_eb00881cf40576cb2793`
- Firestore-backed UI read: PASS
- Silent replay fallback: false
- Receipt and checkpoint signatures, claim chain, and terminal hash: VALID
- Controlled tampered copy: INVALID; production data modified: false

Machine-readable evidence is in `artifacts/ui/live-protected-case.json`, `ui-backend-consistency.json`, and `receipt-verification.json`. Ten 1600x1200 deployed-page captures are in `artifacts/ui/screenshots`.

## Validation

The integration proof checks OPEN/PENDING replay start, refund ALLOW, replacement and duplicate BLOCK, goodwill, Rank 4 non-settlement, Rank 1 settlement, $650/$450 unmanaged economics, $250/$400 protected economics, prohibited “cash saved” wording, live receipt validity, controlled tamper invalidity, and no production mutation.

The UI test suite covers the reducer's backend-snapshot-only behavior, Chronicle rendering, lifecycle and blocked-action presentation, economics, evidence hierarchy, receipt and tamper rendering, reconciliation, TOCTOU, OUTCOME_UNKNOWN, mode labels, loading/error behavior, and lack of frontend economic recomputation.
