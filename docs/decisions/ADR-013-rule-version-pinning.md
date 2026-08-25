# ADR-013: Rule version pinning

## Status

Accepted for Stage 6.

## Decision

Activation pins both `authorization_policy_version` and `evaluation_rule_set_id/version`. Consequential operations and every evaluation retain both references. `current_policy_version` is recorded only for comparison; it cannot reinterpret an active case. The in-process rule catalog rejects replacement of an existing `(rule_set_id, version)`.

A deployment may publish a new version (the proof catalog includes version 2), but an active pact continues resolving its pinned version 1. Migration requires an explicit, audited case transition or trusted exception; routine deployment is not migration.

## Consequences

Historical interpretation is reproducible. Fixes require a new version, and multiple versions may need operational support.
