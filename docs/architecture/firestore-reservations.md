# Firestore reservation layout

## Live database

- Project: `isopact-agentic-20260823`
- Database: `(default)`
- Mode: Firestore Native, Standard edition
- Location: `africa-south1` (Johannesburg)

The regional location was chosen to co-locate with an intended Johannesburg Cloud Run deployment,
reducing write-path distance. App Engine integration is not required and is disabled.

## Documents

```text
pacts/{pact_id}
  operations/{sha256 economic operation identity}
  slots/{slot_name}
  executions/{operation_identity}        # live proof token only
```

The pact document contains trusted activation metadata. An operation document contains canonical
business identity, authorization policy, attempt count, current state, and state history. A slot
document contains the current operation holder. The live proof's execution token is written only
after committed ALLOW and represents one downstream execution; production downstream calls are not
Firestore writes.

There is no global reservation document. Duplicate and exclusive-path contention touches documents
under one pact. Independent pacts therefore do not share a safety lock or a contention document.

## Reservation transaction

The transaction reads the operation and requested slot before writing:

- existing `RESERVED`/`EXECUTING` → `DEFER/OPERATION_IN_PROGRESS`
- existing `OUTCOME_UNKNOWN` → `DEFER/EXTERNAL_OUTCOME_UNKNOWN`
- existing `CONFIRMED` → `BLOCK/DUPLICATE_OPERATION`
- existing `FAILED_AUTHORITATIVELY` → a new authorized attempt
- occupied slot for a different operation → `BLOCK/EXCLUSIVE_RESOLUTION_CONFLICT`
- otherwise create both operation and slot authority → `ALLOW/AUTHORITY_RESERVED`

Firestore can retry the callback. The callback contains only deterministic normalization results and
Firestore reads/writes. It contains no Stripe, carrier, warehouse, CRM, Jira, simulator, or MCP call.

## State and slot release

`FAILED_AUTHORITATIVELY`, `REVERSED`, and `EXPIRED` release the slot. `OUTCOME_UNKNOWN` retains it.
This makes a lost response safe across Gateway process restarts: a new process reads the durable
unknown state and defers instead of recreating the effect.

## Test isolation and cleanup

Live runs use pact IDs derived from a unique `stage4_<timestamp>_<random>` namespace. Cleanup deletes
only the known subcollections and document for each pact created by that run. It never enumerates or
deletes unrelated pact documents.
