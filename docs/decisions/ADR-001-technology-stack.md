# ADR-001: Technology Stack

- Status: Accepted for implementation contract
- Date: 2026-08-23

## Context

IsoPact needs a fast, testable deterministic core, strict schemas, real concurrency proof, asynchronous evidence, a browser demo, and an honest Google Cloud deployment path. The repository is greenfield.

## Decision

- Use Python 3.12+, FastAPI, Pydantic, and pytest for services and the domain core.
- Keep the domain framework-independent behind repository, clock, model, event-bus, signer, and enterprise-tool ports.
- Use Firestore for the MVP authoritative case store and per-pact transactional reservations; use an in-memory adapter for unit tests and the Firestore emulator for local persistence/concurrency tests.
- Use Pub/Sub for production async evidence and a deterministic virtual-clock queue locally. Introduce Cloud Tasks only for a demonstrated deferred-recheck need.
- Use Gemini through the supported Vertex AI SDK for candidate interpretation and plan explanation; use Google ADK for genuinely distinct agents. Deterministic fixtures remain available and prominently labeled.
- Use React + TypeScript for the judge-facing graph/timeline UI.
- Deploy APIs, agents where appropriate, and mock services to Cloud Run. Use Secret Manager, Cloud KMS, and OpenTelemetry/Cloud Logging when implemented and verified.
- Treat Agent Registry, Runtime, Identity, Gateway, Memory Bank, and Model Armor as availability-dependent integrations. Preserve interfaces and document omissions; never fabricate use.

## Consequences

The stack is familiar, emulator-friendly, and separates deterministic safety from cloud/model adapters. Firestore provides the scoped transaction primitive needed for the MVP, but it is not cross-SaaS atomicity and may face per-pact contention. Spanner is only an upgrade path, not an MVP dependency. Google product versions and service availability must be verified from official sources immediately before implementation/deployment stages.

## Rejected alternatives

- Cross-service two-phase commit: external SaaS participants do not provide the required transaction protocol.
- Blockchain: adds no needed trust property to this case and expands scope.
- Spanner in the MVP: unnecessary before measured multi-region/global-ordering requirements.
- LLM-centric policy enforcement: nondeterministic and cannot safely grant consequential authority.
- A workflow engine as the core abstraction: cannot establish correctness across independent agents and external actions outside one planned workflow.
