# Prerequisites

- Python 3.12.x and a fresh virtual environment.
- Node 22.x and npm 10.x; use `npm ci`, never an unpinned install.
- Google Cloud CLI authenticated to `isopact-agentic-20260823` for live inventory/deployment.
- Billing and the APIs in `config/required-google-apis.json` enabled.
- Permissions to inspect Cloud Run, Firestore, Pub/Sub, KMS, Secret Manager, Model Armor, Monitoring, Artifact Registry, IAM, Agent Runtime, and Agent Registry.

Runtime workloads use service/managed identity. Developer ADC is only for explicit operator scripts and is never copied into an image.

