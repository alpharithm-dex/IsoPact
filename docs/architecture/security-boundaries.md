# Security boundaries

IsoPact separates four controls:

| Control | Decides | Does not decide |
|---|---|---|
| Authentication | who presented a valid Google STS identity or signed webhook | whether an economic action is allowed |
| Business authority | capability, precondition, evidence-rank and invariant rules | whether history was later altered |
| Tamper evidence | whether canonical history/checkpoint/receipt changed | whether the source originally told the truth |
| Confidentiality/privacy | who can read secrets and payloads | whether an outcome settled |

## Identity and capability

The Outcome Gateway accepts RS256 only, selects a key from Google STS JWKS, and validates exact issuer, exact audience, expiration, `nbf` when present, required claims and an exact SPIFFE subject-to-Runtime mapping. Request-body `agent_id` is audit-only and cannot grant authority. STS JWTs are bearer credentials and may be reused within their lifetime; IsoPact does not claim one-time token semantics. Semantic operation identity and idempotent reservations prevent a replay from creating a second economic execution.

The dedicated checkpoint signer alone has `roles/cloudkms.signerVerifier` on the signing CryptoKey. Agent Runtime resources, Resolver and Outcome Gateway have no signing permission. The private EC key is generated and retained by Cloud KMS. The evidence ingestor has only Firestore data access and access to the webhook secret. The Model Armor caller has only template-use permission after provisioning.

## Evidence ingress

Stripe-shaped ingress verifies HMAC-SHA256 over `timestamp.raw_body`, uses constant-time comparison and enforces a five-minute timestamp window before parsing into Rank 1 evidence. Missing, stale, invalid or source-mismatched signatures never call the evidence pipeline. The live secret is stored in Secret Manager with user-managed replication in `africa-south1`; resource names, public keys, service URLs and region names remain ordinary configuration.

## Model-facing text

Only untrusted text crossing into the Gemini Pact Compiler or Resolver is screened. Model Armor is not placed in the Gateway, invariant engine, evidence reducer, KMS signer or verifier. A detection defers model reasoning. An API failure also fails closed for these model-facing paths, while deterministic enforcement remains available and unchanged. Screening logs retain operation/reference, template, outcome, categories, timestamp and input hash—not the full input.

Model Armor supports `europe-west1` for this project API surface whereas `africa-south1` was not advertised. This sends the minimized model-facing text to the reasoning-plane region and must be treated as a residency boundary. The settlement plane, Firestore, gateway, Secret Manager replication and KMS remain in `africa-south1`.

## Privacy

Cross-region agent requests contain pact/order reference, action, integer amount/currency, request/session/trace identifiers and the minimum task text. They exclude payment instruments, webhook material, KMS private material, service credentials and full internal records. Demonstration subject IDs remain intentionally readable for traceability; sensitive payloads are hashed or referenced.
