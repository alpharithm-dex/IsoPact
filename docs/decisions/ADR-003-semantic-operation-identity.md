# ADR-003: Semantic Operation Identity

- Status: Accepted and implemented for Stage 1
- Date: 2026-08-23

## Context

Transport-level deduplication is insufficient: two agents can request the same refund with different request, trace, and session IDs. Conversely, refund and replacement are distinct operations even though policy makes them mutually exclusive.

## Decision

The deterministic economic identity contains exactly:

```text
pact_id
resolution_path
canonical event_type
authoritative target subject_id
normalized value (currency + integer minor units) or normalized resource
```

Canonical JSON uses sorted keys and compact separators; its UTF-8 bytes are SHA-256 hashed. Identifiers use explicit deterministic normalization. Currency is uppercase and monetary values are integer minor units, so `200`, `200.00`, and `$200.00 USD` normalize to `USD:20000`. A `$50` partial refund remains distinct.

Excluded fields are HTTP/MCP request ID, agent ID, session ID, trace ID, timestamps, and policy version. These fields are retained for audit but cannot alter economic identity. Policy version is authorization metadata: the pact pins it and each reservation attempt records it. An old live, confirmed, or unknown reservation remains blocking after a policy update. Only authoritative failure permits an explicit retry of the same operation key under the currently pinned policy.

Resolution exclusivity is separate. Refund and replacement have different operation keys but acquire the same per-pact `primary_compensation` slot. Authorized goodwill has its own slot.

## Risks

Collision risk from SHA-256 is negligible relative to application risks; canonical-field collision is the material concern. Over-normalization could merge distinct subjects/resources. Under-normalization could separate equivalent operations through aliases, currency representation, identifier case, or resource spelling. Stage 1 therefore accepts only explicit authoritative identifiers and closed canonical action names.

Future semantic correlation may propose that incomplete/aliased records refer to one subject, potentially using Gemini. That correlation is not canonicalization and cannot itself grant execution authority. It must resolve to an explicit subject or human-confirmed link before a consequential reservation.
