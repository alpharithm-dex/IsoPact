# Recovery and limitations

- **Cloud Run:** rebuild from the Dockerfile, deploy the manifest digest/config, then run `verify_deployment.py`.
- **Agent Runtime:** recreate from `scripts/deploy_agent_fleet.py`, update the exact four manifest resources, re-register, and rerun identity/security proofs.
- **Pub/Sub subscription:** recreate against the canonical topic with documented retention/ack settings; evidence truth remains in Firestore.
- **Lost developer machine:** recover from the release source snapshot and cloud identities; no workstation secret is required by runtime.
- **Model Armor unavailable:** model-facing paths fail safely; deterministic policy remains authoritative.
- **KMS unavailable:** settlement truth may be SETTLED while receipt issuance remains honestly pending/failed; no unsigned receipt is represented as signed.
- **Telemetry unavailable:** enforcement remains active; telemetry is non-authoritative.

Firestore is authoritative but not immutable. Repository rules prevent semantic mutation and signed checkpoints detect later tampering. Live inventory shows PITR disabled and one-hour version retention. A production rollout should enable appropriate backups/PITR, retention/export, and external immutable checkpoint archival. None is claimed as currently implemented.

