# ADR-015: Protected Value accounting

## Status

Accepted for Stage 6.

## Decision

Protected Value is event-based, not rule-impact-based. Each event is typed as `INVALID_ACTION_PREVENTED`, `AUTHORIZED_VALUE_RECOVERED`, or `LEGITIMATE_VALUE_DELAYED` and has a stable identity derived from type, economic object, operation, amount, and currency. Multiple rules firing for one blocked action cannot duplicate its contribution.

The formula is prevented + recovered − legitimate delay. The Stage 4 replay therefore reports `$400 projected invalid value prevented`: one blocked $200 replacement and one blocked $200 duplicate refund. It does not claim cash saved. Allowed goodwill contributes no protected value.

Pre-existing divergence is not prevention. A reversible $200 replacement is a recovery candidate, but recovered value stays zero until compensation and authoritative evidence exist. A false block of a legitimate $50 partial refund records negative $50.
