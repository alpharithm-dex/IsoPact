# Stage 8 evidence — Google ADK agent fleet

- Status: BLOCKED on Agent Registry indexed skills / A2A runtime compatibility

The remote consequential tools deliberately stop at `CONTROL_PLANE_SUBMISSION_REQUIRED`; they do not claim a Gateway execution. The typed in-process adapters and deterministic replays do execute through the Stage 4 Gateway, but a live remote Agent Runtime-to-Gateway submission endpoint is not deployed. This is a second strict Gate 8 blocker rather than an integration claim.

The machine-readable source of truth is `artifacts/agents/fleet-summary.json`. The proof uses Google ADK 2.7.1, `gemini-3.5-flash`, project `isopact-agentic-20260823`, and Agent Runtime `europe-west1`. Vertex model inference is explicitly routed to the verified global endpoint.

Each remote resource requests and reports `AGENT_IDENTITY`; `effective_identity` is captured and mapped to the logical IsoPact agent ID, authority role, and published skill. Agent Registry automatically discovered the deployed resources and exposed authenticated runtime references. Registry protocol metadata is reported exactly: the object-deployed ADK apps use `CUSTOM` HTTP/JSON rather than A2A. A real Google `A2aAgent` deployment was attempted and rejected by the runtime's unsupported `a2a_extension` mode; `support-a2a-deployment.json` records the resource and error.

Live invocations are separate from deterministic fixtures. They must include actual Gemini events, function calls, function responses, and final text. Deterministic artifacts prove one winner in the concurrent Support/Fulfillment primary race, one execution across two Support sessions, Rank 4 agent text remaining PENDING, identity denials, trusted goodwill limits, and failure isolation.

The evaluation file contains 26 cases across refund, replacement, goodwill, duplicate sessions, primary concurrency, pending evidence, pre-existing divergence, approval, irreversible conflict, ambiguous context, hallucinated completion, authority misuse, TOCTOU, unregistered compensation, stale session state, and model failure. Agent local-mission success and IsoPact safety success are separate fields.

Memory Bank is not integrated and no authoritative data is stored in agent memory. No cryptographic receipt, frontend, Stage 9 work, or final benchmark is included.
