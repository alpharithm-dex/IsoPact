# Public claims ledger

Every headline claim must match the machine-readable ledger in `artifacts/submission/claims-ledger.json`.

| ID | Classification | Public wording | Scope and caveat | Evidence |
|---|---|---|---|---|
| CL-001 | VERIFIED | Four specialized Google ADK agents are deployed to Gemini Enterprise Agent Runtime. | Four named reasoning engines in `europe-west1`. | `artifacts/agents/runtime-deployments.json` |
| CL-002 | VERIFIED | Runtime agents use managed Agent Identity. | Runtime identity evidence; not Cloud Run IAM authentication. | `artifacts/agents/registry-final.json` |
| CL-003 | VERIFIED | Consequential live agent actions traverse the remote IsoPact Outcome Gateway. | Runtime STS JWT validated at the application boundary. | `artifacts/agents/stage8b-gate.json` |
| CL-004 | VERIFIED | Firestore stores authority and Pact Graph state in `africa-south1`. | Firestore is not immutable; PITR/delete protection disabled. | `artifacts/release/cloud-inventory-raw.json` |
| CL-005 | VERIFIED | Pub/Sub transports authoritative evidence. | Canonical topic plus retained proof subscription. | `artifacts/observability/stage10c-gate.json` |
| CL-006 | VERIFIED | Gemini 3.5 Flash compiles Pact intent and reasons about constrained reconciliation. | Gemini proposes; deterministic code authorizes. | Stage 3/7/8 artifacts and deployment inventory |
| CL-007 | VERIFIED | Deterministic logic owns consequential authorization. | Models cannot authorize refunds or invent compensation types. | Stage 4/6/7 tests and Stage 12 benchmark |
| CL-008 | VERIFIED | Model Armor screens model-facing untrusted input. | Defense in depth; correctness does not rely on perfect screening. | `artifacts/agents/stage8b-gate.json` |
| CL-009 | VERIFIED | Memory Bank stores non-authoritative cross-session context. | Stale context cannot override authoritative evidence or policy. | `artifacts/agents/fleet-summary.json` |
| CL-010 | VERIFIED | KMS signs provenance checkpoints and settlement receipts. | Proves recorded-history integrity, not source truthfulness. | `artifacts/security/stage9-gate.json` |
| CL-011 | VERIFIED | OpenTelemetry and Google Cloud observability reconstruct causal execution. | Telemetry is not required for authority. | `artifacts/observability/stage10c-gate.json` |
| CL-012 | VERIFIED | Frozen Stage 12 contradiction recall and precision are 100%. | Bounded benchmark; Wilson CI 94.34%–100%. | `artifacts/benchmark/stage12-summary.json` |
| CL-013 | QUALIFIED | Reconciliation benchmark success is 100%. | Only five eligible cases; CI is wide. | `artifacts/benchmark/stage12-summary.json` |
| CL-014 | QUALIFIED | The canonical scenario prevents $400 of projected invalid value. | Scenario projection; not realized cash savings. | `artifacts/ui/live-protected-case.json` |
| CL-015 | QUALIFIED | Semantic duplicate execution is prevented. | Under modeled operation identity; not universal exactly-once delivery. | Stage 4 concurrency and Stage 12 benchmark |
| CL-016 | QUALIFIED | The public release is production-readiness audited. | Hackathon release, not formal certification; known risks documented. | `docs/evidence/stage-13-production-readiness.md` |
| CL-017 | DO_NOT_CLAIM | $400 cash saved. | Use “$400 projected invalid value prevented.” | Claims audit |
| CL-018 | DO_NOT_CLAIM | Cross-SaaS ACID or distributed transaction atomicity. | IsoPact provides application-level outcome isolation. | Architecture contract |
| CL-019 | DO_NOT_CLAIM | Agent Gateway mediates production traffic. | It is provisioned/default-deny/not bound. | `artifacts/agents/agent-gateway-probe.json` |
| CL-020 | DO_NOT_CLAIM | A2A is used for canonical production communication. | A2A skills are absent from current Runtime registry entries. | `artifacts/agents/registry-final.json` |
| CL-021 | DO_NOT_CLAIM | Firestore storage is immutable. | Hash chains and KMS make edits detectable; deletion remains possible. | Stage 9 and recovery docs |
| CL-022 | DO_NOT_CLAIM | IsoPact has 100% accuracy. | Report frozen benchmark metrics and intervals only. | Stage 12 summary |
| CL-023 | DO_NOT_CLAIM | Production throughput was benchmarked. | Separate component, deployed, and contention measurements. | Stage 12 plus live contention evidence |
| CL-024 | DO_NOT_CLAIM | Strict end-to-end African data residency. | Reasoning is in Europe; settlement/data plane is in Africa. | Deployment manifest |
| CL-025 | DO_NOT_CLAIM | The benchmark covers every enterprise domain. | Current workload and Compensation Registry are commerce-focused. | Benchmark manifest |
