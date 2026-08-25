# Stage 13 production-readiness evidence

Stage 13 is complete with a passing live deployment verification and a documented set of residual architectural risks. This is a production-readiness audit for the hackathon release, not a claim of formal certification.

## Canonical release

- Release: `v0.1.0-hackathon`
- Project: `isopact-agentic-20260823`
- Cloud Run revision: `isopact-outcome-gateway-00024-qnr`, 100% traffic
- Image: `sha256:f9d507b92942cb739522f6572ae6f94c9b64835575454d83e617e79ee00d7332`
- Source revision: `NOT_A_GIT_CHECKOUT`; the release manifest supplies a deterministic tree SHA-256 instead.
- Clean Cloud Build: `c4b6db26-0c42-46a8-82d5-c0018a3e7dbc`
- Independent clean-room proof build: `95f996d2-0a63-4287-84a1-66f68467ba01`, digest `sha256:6293aaaf1ac6c8927d319019b0c9b27e6a0d93bcf93cd2c804ebca9bd4c0e3f6`.

## Verification results

`python scripts/release_verify.py` passed every non-destructive gate: secret scan, 117 backend tests plus five subtests, 12 frontend tests, frontend production build, live inventory, live deployment/auth/security verification, signed-receipt verification, deterministic benchmark smoke, advisory audit, and SBOM generation.

The isolated clean-room run installed only the committed Python and npm locks in a new directory and passed the same backend/frontend build, receipt, and deterministic replay checks. The first attempt is retained as evidence of an external PyPI timeout; the second fresh attempt passed.

## Security and supply-chain disposition

- Secret scan: 395 files, zero genuine credentials.
- npm audit: zero vulnerabilities.
- Python audit: four findings in `cryptography 46.0.7`, each assessed as unreachable in IsoPact's ECDSA-only application paths. The OpenSSL wheel advisory was checked against the official 2026-06-09 advisory. Any expansion into PKCS7/S-MIME, CMS, QUIC, OCSP, CMP, DHX, certificate-chain construction, or specialized cipher APIs requires reassessment before release.
- Container vulnerability scanning was unavailable from the Windows on-demand scanning client and unsupported in the selected regional invocation. The immutable digest, exact top-level production pins, SBOM, Python audit, npm audit, and clean Cloud Build are compensating controls—not a substitute for a registry-native container scan.
- The SBOM is CycloneDX 1.5 evidence, not formal certification or attestation.

## Drift and residual risks

The desired/live comparison has no unresolved canonical difference. Historic revisions/images and the Stage 10C proof job remain intentionally. The Agent Gateway remains default-deny but unbound, so it must not be described as mediating canonical traffic.

The project default Compute Engine service account retains `roles/editor`. Canonical workloads use dedicated service accounts and managed agent identities. The role was not removed because Cloud Build currently uses that identity and no replacement migration was validated during this stage.

Firestore PITR and delete protection are disabled; retention is one hour. Recovery therefore relies on replayable signed evidence and deployment rollback, not point-in-time database recovery. Firestore documents are not storage-level immutable. KMS or telemetry outages fail closed or degrade observability as described in the recovery runbook.

## Evidence index

- `artifacts/release/final-verification.json`
- `artifacts/release/deployment-verification.json`
- `artifacts/release/clean-room.json`
- `artifacts/release/cloud-resources.json`
- `artifacts/release/deployment-drift.json`
- `artifacts/release/vulnerability-audit.json`
- `artifacts/release/secret-scan.json`
- `artifacts/release/sbom.cdx.json`
- `artifacts/release/release-manifest.json`
- `docs/security/final-iam-audit.md`
- `docs/security/public-attack-surface.md`
- `docs/deployment/recovery.md`
