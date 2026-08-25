# Stage 8B live enterprise fleet evidence

Status: PASS

## Live resources

- Four canonical ADK agents remain on Google Agent Runtime in `europe-west1`,
  each with managed Agent Identity.
- Four automatic Agent Registry records report framework `google-adk` and empty
  A2A skill arrays, correctly reflecting non-A2A deployments.
- `isopact-outcome-gateway` revision `00004-7nv` serves the typed authenticated
  action facade from Cloud Run in `africa-south1`.
- Firestore reservations and Pact Graph authority remain in `africa-south1`.
- Google Agent Gateway `isopact-egress` exists in `europe-west1`, mode
  `AGENT_TO_ANYWHERE`, associated with the regional Registry, and remains
  intentionally default-deny/unbound pending a complete safe Runtime allowlist.

## Proof results

The remote Support smoke created one PENDING refund through the authenticated
Cloud Run service. A concurrent Runtime race produced one primary external
execution: Fulfillment won replacement and Support lost with
`EXCLUSIVE_RESOLUTION_CONFLICT`. Two Support sessions generated one refund;
the second received `DUPLICATE_OPERATION`.

Temporary diagnostic tools on the same three canonical resources proved live
network denials: Support-to-replacement, Fulfillment-to-refund, and
Retention-to-refund all returned HTTP 403 `CAPABILITY_DENIED` before pact lookup
with zero external calls. The tools were then removed and the canonical agents
updated in place back to least privilege.

The complete case is pact
`pact_stage8b-e2e-20260824021629_04353dc6e7acd4db209b`. Support created one
$200 PENDING refund; Fulfillment replacement was blocked; Retention issued $50
goodwill; a second Support session was blocked as duplicate; the agent's
completion statement remained Rank 4 and the Pact remained PENDING. A verified
`stripe.refund.succeeded` Rank 1 event changed the Pact to SETTLED. External
objects: one refund, zero replacements, one $50 goodwill. Authorized
compensation is $250 and projected protected value is $400.

The combined proof revealed and fixed an additive-remedy reducer defect:
goodwill no longer replaces the selected primary refund. Both in-memory and
Firestore reducers now select only paths in the `primary_compensation` slot.

Memory Bank stored/retrieved non-authoritative context across sessions. A stale
memory sentence claiming two refunds were allowed did not mutate policy; the
second refund was blocked and external refund count stayed one.

Cleanup removed four exact exploratory Runtime resources, their obsolete child
sessions, and the exploratory `isopact-pact-status` Cloud Run service. Only the
four canonical Runtime agents remain; historical JSON evidence was retained.

## Verification

- `python -m unittest discover -s tests -v`: 94 tests, OK.
- Stage 8 evaluation artifact validation: 26/26 passed.
- Live Stage 8B summary: all identity, race, duplicate, spoofing, and Rank 1
  settlement booleans true.
- No credential-shaped files or private keys are part of the source tree.

Primary artifacts are in `artifacts/agents/`: `remote-action-proof.json`,
`remote-primary-race.json`, `remote-duplicate-support.json`,
`remote-claim-vs-evidence.json`, `end-to-end-remote-case.json`,
`stage8b-live-role-denials.json`, `registry-final.json`, `skill-registry.json`,
`memory-bank-proof.json`, `agent-gateway-probe.json`, `stage8b-latency.json`,
`stage8b-data-sovereignty.json`, and `resource-cleanup.json`.
