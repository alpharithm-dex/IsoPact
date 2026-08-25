# ADR-019: Specialized agent boundaries

- Status: Accepted
- Date: 2026-08-24

## Decision

Support, Fulfillment, Retention, and Resolver are separate ADK agents with immutable role identities and materially different tool inventories. Capability denial is deterministic and precedes tool execution. Agents never receive repositories, transaction primitives, raw downstream adapters, policy mutation, or arbitrary compensation execution.

## Consequences

Each worker can optimize a plausible local mission while IsoPact arbitrates global conflict. Adding a role or capability requires code and tests; prompt changes cannot grant authority.

