# ADR-020: Agent state is not business state

- Status: Accepted
- Date: 2026-08-24

## Decision

ADK sessions and model text have no settlement authority. Memory Bank is not integrated in Stage 8. Pact Graph, reservations, trusted policy, and ranked evidence remain the only business-authority stores described by the system contract.

## Consequences

Agent retry, stale conversation, hallucination, or outage cannot settle a pact, release authority, change a limit, or approve compensation. Session identity is excluded from semantic operation identity.

