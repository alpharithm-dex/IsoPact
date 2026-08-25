# ADR-017: Execution-time preconditions

## Status

Accepted for Stage 7.

## Decision

Planning and validation state are audit facts, not permanent authority. Immediately before each compensation, IsoPact re-fetches source-of-record state and evaluates the registry definition without a model call. Approval does not waive this check.

The audit records planned, validated, and executed-against states plus the machine precondition result. If a carrier label changes `CREATED → ACCEPTED`, cancellation is not called and execution becomes `PRECONDITION_FAILED`. Dependencies are also deterministic: warehouse release requires carrier cancellation confirmation.

## Consequences

Safe races may require escalation and leave a conflict unresolved. Gemini is not called to improvise another consequential action.
