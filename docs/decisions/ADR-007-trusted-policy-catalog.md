# ADR-007: Deterministic Trusted Policy Catalog

- Status: Accepted and implemented
- Date: 2026-08-23

## Context

A candidate must be enriched with business limits and evidence requirements, but allowing natural language or Gemini to choose arbitrary policy would turn interpretation into authorization.

## Decision

The authoritative tuple `(tenant, domain, case_type)` selects policy deterministically. For the MVP:

```text
(demo-retailer, commerce, missing_order) -> commerce_missing_order_v1@1
```

The catalog supplies `resolve_missing_order`; refund/replacement/goodwill concept mappings; `primary_compensation`; `$50 USD` maximum goodwill; `stripe.refund.succeeded`; `carrier.shipment.accepted`; `$250` consequential approval threshold; and duplicate-compensation blocking. Candidate text cannot add, remove, or override catalog fields.

Unknown mapping rejects the compilation. Known policy plus unresolved ambiguity produces no draft. Explicit order/customer/ticket identifiers must match authoritative context; semantic matching is not used in Stage 3.

## Consequences

Policy changes require trusted code/config review and versioning. The in-code Stage 3 catalog is intentionally narrow; durable tenant configuration, policy signatures, and rollout controls belong to later hardening stages.
