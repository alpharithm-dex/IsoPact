# ADR-024: Canonical per-pact StateClaim chains

Status: Accepted

Use IsoPact Canonical JSON v1 and SHA-256 predecessor-linked claims scoped to one pact. Allocate sequence and predecessor in a Firestore transaction on the pact root. Reject floats and semantic mutation; represent state changes by appending claims.

This gives deterministic cross-process bytes, detects edit/delete/reorder/injection and avoids a global enterprise serialization bottleneck. The cost is a hot pact-root document under high concurrency; transaction retry and bounded backoff are required. Hashing is tamper evidence, not confidentiality, authentication or business authority.
