# ADR-030: Telemetry privacy and cardinality

Accepted. Production model content capture is disabled. JWTs, authorization headers, webhook material, customer messages, payment instruments, private keys, and raw prompts are filtered from custom telemetry. Unique case identifiers are allowed only in traces/logs, never metric dimensions. Metric labels are enforced by an allowlist.
