# Stage 12 adversarial benchmark

Benchmark `stage12-v1.0.0` executed 130 deterministic cases (66 valid, 64 invalid), including 39 held-out cases, plus 2,500 generated economic/property cases. All A–Z families remain in the result corpus.

## Results

- Contradiction recall and precision: 100%.
- Legitimate approval: 100%; false blocks: 0%.
- Duplicate consequential executions, unsupported closures, unsafe compensations, OUTCOME_UNKNOWN duplicates, model authority mutations, forged Rank 1 events, and undetected tampering: zero.
- Eligible reconciliation: 5/5 successful, with no premature recovered value.
- Receipt integrity: 3/3 issued deterministic benchmark receipts valid.
- Concurrency: 100 primary races, 100 duplicate races, and 50 independent pacts; no dual winner, duplicate execution, or cross-pact interference.
- Provenance levels 1/2/5/10/25: no forks, gaps, or duplicate sequence numbers. The increased artificial same-pact latency is disclosed and is not a throughput claim.
- Live-cloud checks: 20 Firestore-backed reads through the deployed Cloud Run service. These validate preserved cloud evidence and are explicitly not represented as 20 newly mutated pacts.
- Live Gemini evidence: five Compiler plus five Resolver calls, all schema-valid and semantically valid; no registry escape or approval bypass.

Wilson 95% intervals are in `confidence-intervals.json`; component latency distributions are in `latency.json`. There were no failed cases to explain. The canonical $650/$450 unmanaged and $250/$400 protected demo contract remains unchanged.

## Scope warning

This is a bounded adversarial proof workload, not production-scale load testing. Local deterministic timings, deployed read latency, historic live-model timings, and artificial same-pact contention must not be combined into a general throughput claim.
