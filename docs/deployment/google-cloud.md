# Google Cloud deployment

Desired state is `config/deployment-manifest.json`; required services are `config/required-google-apis.json`. Run `scripts/provision/enable_required_apis.ps1`, then use existing idempotent provisioning scripts for Stage 5/8/9/10 resources. Existing resources and IAM bindings are treated as success; signing keys and versions are never rotated or deleted by routine deployment.

Build with Cloud Build and deploy the immutable digest, not `latest`. `scripts/deploy/deploy_gateway.ps1` reads the manifest and updates the existing Cloud Run service. The service is network-public because Runtime STS tokens are verified at the application boundary. Missing/invalid tokens return 401; role-capability denial returns 403.

The Agent Gateway exists in default-deny, unbound mode. Canonical traffic is not claimed to traverse it. Four Agent Runtime resources and their Agent Registry records are canonical.

