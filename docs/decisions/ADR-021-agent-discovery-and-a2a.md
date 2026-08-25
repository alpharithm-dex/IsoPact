# ADR-021: Agent discovery and A2A

- Status: Accepted with an explicit protocol boundary
- Date: 2026-08-24

## Decision

Use Agent Runtime automatic Agent Registry publication for deployed ADK resources. Capture registry resource, runtime identity, runtime reference, protocol, and endpoint. Publish each logical skill in the runtime resource description and local fleet manifest.

The object-deployed `AdkApp` resources are advertised by Agent Registry as authenticated `CUSTOM` HTTP/JSON query interfaces, not `A2A_AGENT`. IsoPact does not manufacture an agent card or label those endpoints A2A. A genuine Google `A2aAgent` Support deployment with a real Agent Card was attempted using `EXPERIMENTAL` server mode. Resource `4651998512748167168` failed because the regional runtime server rejected the SDK's `a2a_extension` operation mode. This product/runtime mismatch is captured; no fake endpoint or fallback A2A claim is made.

## Consequences

Stage 8 proves live managed discovery and remote interoperation through Agent Runtime's supported API. It reports A2A as not exposed by this deployment mode. Consumers can reliably distinguish discovery metadata from protocol compliance.
