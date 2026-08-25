# Remote action plane

Stage 8B separates model reasoning from consequential execution:

```text
ADK agent on Agent Runtime (europe-west1)
  -> audience-bound Google Agent Identity STS JWT
  -> IsoPact Outcome Gateway / typed HTTPS API (Cloud Run, africa-south1)
  -> existing IsoPactGatewayInterceptor
  -> Firestore semantic reservation
  -> narrow enterprise adapter
  -> Firestore Pact Graph claim/evidence pipeline
```

The Cloud Run facade exposes health, minimal pact status, refund, replacement,
goodwill, and validated resolution-plan routes. It exposes no arbitrary tool,
raw Firestore mutation, policy mutation, reservation override, or settlement
override route. Consequential calls delegate to the Stage 4 interceptor.

## Authentication and authority

Each Runtime resource obtains a short-lived, audience-bound token from Google's
runtime identity facility. Cloud Run validates its RS256 signature from the
Google STS issuer JWKS, exact issuer, exact Outcome Gateway audience, expiry,
and exact per-resource SPIFFE subject. The subject maps to one logical agent and
role before request JSON is read. Body `agent_id` is audit-only and cannot grant
authority. The deterministic capability policy then authorizes the requested
operation. Cloud Run's network ingress is public only because Cloud Run IAM did
not accept the Agent Runtime STS workload token; application ingress remains
fail-closed and rejects missing, invalid, or unmapped tokens before pact access.

Agents carry no static secret and no Firestore client. They receive only typed
tool responses, never an unrestricted Pact Graph or persistence handle.

## Google Agent Gateway boundary

Google Agent Gateway and the IsoPact Outcome Gateway are different resources.
The regional Google Agent Gateway `isopact-egress` was created in default-deny
Agent-to-Anywhere mode and is attached to the europe-west1 Agent Registry; the
Outcome Gateway was registered as its target inventory endpoint. It was not
bound to the four canonical agents: Google's documented binding redirects all
Runtime egress and requires an IAP authorization extension plus allowlisting of
LLM, Agent Registry, telemetry, sessions, Memory Bank, and destination variants.
Binding before that complete allowlist would break the proven fleet. Thus the
resource remains default-deny/preparatory, and no mediated traffic claim is made.
The production Stage 8B path is the separately authenticated IsoPact Outcome
Gateway.

Evidence: `artifacts/agents/remote-action-proof.json`,
`stage8b-live-role-denials.json`, and `agent-gateway-probe.json`.

