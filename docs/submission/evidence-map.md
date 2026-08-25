# Judge evidence map

| Claim / judge question | Proof | Artifact |
|---|---|---|
| Competing agents cannot both win primary authority | Stage 4 concurrency; Stage 8 remote race; Stage 12 repetitions | `artifacts/gateway/summary.json`, `artifacts/agents/stage8b-gate.json`, `artifacts/benchmark/stage12-summary.json` |
| Agent statements cannot settle the business | Stage 5 evidence hierarchy; live fleet/UI | `artifacts/evidence/summary.json`, `artifacts/ui/live-protected-case.json` |
| Transport retries cannot bypass semantic identity | Operation and resolution-slot tests | Stage 4 tests and benchmark duplicate suite |
| Lost responses do not trigger blind retries | Persistent `OUTCOME_UNKNOWN` and reconciliation | Stage 2/4 failure artifacts; Stage 12 failure injection |
| Gemini has no consequential authority | Compiler draft validation and deterministic gateway/registry | Stage 3 compiler artifacts; Stage 6/7 tests |
| Four specialized Runtime agents are live | Deployment and registry inventory | `artifacts/agents/runtime-deployments.json`, `artifacts/agents/registry-final.json` |
| Runtime identity is fail-closed | Invalid-token 401 and wrong-role 403 | `artifacts/release/deployment-verification.json`, `artifacts/security/gateway-auth-attacks.json` |
| Firestore holds Pact Graph authority | Live resource inventory and repository tests | `artifacts/release/cloud-inventory-raw.json`, `artifacts/evidence/summary.json` |
| Evidence is ranked and source-specific | Evidence reducer tests and live Rank 1 settlement | `artifacts/evidence/summary.json`, UI screenshot shortlist |
| Tampering is detected | Hash chain, KMS checkpoint, valid/tampered receipt | `artifacts/security/stage9-gate.json`, `artifacts/ui/receipt-verification.json` |
| Stale plans do not execute | TOCTOU revalidation with zero cancellation calls | `artifacts/ui/screenshots/10-toctou-safe-refusal.png` and resolver tests |
| Telemetry is causal but non-authoritative | Real Pub/Sub span link and failure isolation | `artifacts/observability/stage10c-gate.json` |
| Model-facing content is not traced | NO_CONTENT marker scan | Stage 10B/10C privacy evidence |
| Benchmark metrics are scoped | Frozen corpus, held-out split, properties, failures, CIs | `artifacts/benchmark/stage12-summary.json`, `artifacts/benchmark/benchmark-manifest.json` |
| Release is reproducible | Exact locks, clean room, Cloud Build, SBOM, digest | `artifacts/release/clean-room.json`, `artifacts/release/final-verification.json`, `artifacts/release/sbom.cdx.json` |
| Known risks are not hidden | IAM, public surface, recovery, production readiness | `docs/security/final-iam-audit.md`, `docs/deployment/recovery.md`, `docs/evidence/stage-13-production-readiness.md` |

Start with `docs/submission/hostile-judge-audit.md` for adversarial answers and `artifacts/submission/claims-ledger.json` for machine-readable public-claim scope.
