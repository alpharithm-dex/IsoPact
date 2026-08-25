# Stage 12 methodology

The acceptance contract was written before execution. The corpus uses a frozen 70/30 development/held-out rule and independent expected/observed code paths. Any future ground-truth correction requires a benchmark-version increment and full held-out rerun.

The deterministic suite runs twice and compares semantic-result SHA-256 hashes. Property testing uses 2,500 stable-seed generated cases and integer minor units plus `Decimal`; it permutes amounts, partial refunds, goodwill boundaries, and resolution combinations. Concurrency is bounded—not a production load test—with 100 refund/replacement races, 100 duplicate-refund races, and 50 independent pacts.

Proportions use two-sided Wilson 95% score intervals. Latencies are reported by component as p50, p95, maximum, and sample count. Synthetic/local timings, deployed HTTP timings, previous live Gemini latency evidence, and artificial same-pact contention are not conflated.

The 20-check cloud subset calls the current deployed Cloud Run interface. Each request performs a live Firestore-backed pact read; scenario/security/evidence categories are validated against authoritative artifacts already generated through Pub/Sub, KMS, Vertex AI, and Cloud Trace. This subset is a proof/availability benchmark, not 20 newly mutated production pacts. Ten existing live Gemini calls—five Compiler and five Resolver—are revalidated semantically from their preserved live evidence.

False blocks and missed contradictions are retained by case ID. Protected Value uses mutually exclusive prevented, recovered, and legitimate-delayed categories; delayed value is never positive protection.

