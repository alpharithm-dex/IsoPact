# Resource inventory and footprint

The live machine-readable inventory is `artifacts/release/cloud-resources.json`; raw query results are retained separately. Classifications are CANONICAL, PROOF/TEST, OPTIONAL, or OBSOLETE. There are no UNKNOWN entries.

Cost drivers are Agent Runtime invocations, Gemini calls, Cloud Run, Firestore reads/writes/storage, Pub/Sub delivery, KMS operations, Model Armor screening, Monitoring/Trace ingestion, Memory Bank usage, Cloud Build, and Artifact Registry storage. This is a hackathon proof workload, not a production cost benchmark; no monthly estimate is asserted.

Historic Cloud Run revisions and images are retained as platform-managed proof history. The Stage 10 proof job and narrowly scoped Pub/Sub grants are retained for maintained observability regression. No cleanup action deletes receipt evidence or historic KMS verification versions.

