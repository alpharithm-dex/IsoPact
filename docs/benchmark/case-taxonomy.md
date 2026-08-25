# Stage 12 case taxonomy

The `stage12-v1.0.0` corpus contains 130 deterministic cases: five stable-seed variants for each family A–Z. Sixty-six cases are legitimate and sixty-four are invalid/conflicting. Thirty-nine cases are held out by the frozen deterministic split rule; observed results never generate expected truth.

| Families | Coverage |
|---|---|
| A–F | normal resolutions, primary conflicts, partial-refund and goodwill boundaries, semantic duplicates, truly distinct operations |
| G–L | concurrency, pre-existing divergence, safe and irreversible reconciliation, TOCTOU, OUTCOME_UNKNOWN/restarts |
| M–R | evidence ordering and duplication, forged evidence, agent claims, model failure, memory poisoning |
| S–Z | Firestore/Pub/Sub/KMS/telemetry failures, identity attacks, provenance tampering, policy pinning, pact isolation |

`cases.json` holds identities and split metadata. `ground-truth.json` separately holds expected actions, conflicts, execution counts, settlement, reconciliation eligibility, authority requirements, and Protected Value. Seeds, scenario, policy, rule, and benchmark versions are recorded per case.

