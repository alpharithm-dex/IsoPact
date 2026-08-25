# Final IAM audit

Canonical workloads use four Agent Runtime managed identities, `isopact-outcome-gateway@`, and the proof-specific `isopact-stage10c-proof@` identity. The Gateway does not run as the default Compute service account.

The default Compute service account retains project `roles/editor`. No canonical runtime uses it, but Cloud Build/deployment history may depend on it. It is classified as a **PRE-EXISTING PROJECT RISK** and was not removed without a separately validated replacement-role migration. Project owners are human operator accounts, not workloads.

The Stage 10 proof identity retains `roles/pubsub.publisher` on only `isopact-stage5-evidence` and `roles/pubsub.subscriber` on only `isopact-stage5-evidence-proof`. The proof job remains an intentional observability regression workflow, so these grants are retained; there is no project-wide Pub/Sub role for it.

Final live IAM and service account data are in `artifacts/release/cloud-inventory-raw.json`. Any broad role must be reassessed before a non-hackathon production rollout.

