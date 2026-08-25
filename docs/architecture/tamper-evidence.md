# Tamper-evident pact history

Stage 9 adds integrity and provenance without changing Stage 1–8 settlement semantics. Authorization, evidence rank, invariant evaluation, resolution and settlement remain deterministic controls. A hash or KMS signature cannot make an unauthorized action valid or an unauthenticated source authoritative.

## Canonical StateClaim

IsoPact Canonical JSON v1 is UTF-8 JSON with lexicographically sorted object keys, no insignificant whitespace, JSON booleans/null, and no ASCII escaping. Object keys must be strings. Floating-point numbers and NaN/Infinity are rejected; economic values are integer minor units. The hash body excludes only `claim_hash` and includes the schema version, identity, sequence, predecessor, timestamps, trace and operation/source identifiers, evidence/policy/rule references, normalized payload, its digest and protected references.

`normalized_payload_hash` is SHA-256 over canonical normalized payload bytes. Each pact begins with `SHA256("isopact:stateclaim:genesis:v1")`. For sequence n:

`claim_hash[n] = SHA256(hex_decode(previous_claim_hash) || canonical_claim_body[n])`

Sequence allocation, predecessor selection, claim creation and root terminal-hash update occur in one Firestore transaction on the pact root. This intentionally creates a per-pact serialization point, not an enterprise-global chain. Firestore retries plus bounded application retry handle contention. Repository writes with an existing claim ID are idempotent only when the semantic fingerprint is identical; otherwise they fail with `COMMITTED_CLAIM_SEMANTIC_MUTATION_REFUSED`. A changed state is appended as a new claim.

## Checkpoints and rollback resistance

A signed checkpoint commits to the pact, terminal claim hash, sequence/count, evidence identifiers, economic snapshot digest, invariant digest and policy/rule versions. The final receipt commits to the checkpoint ID, terminal hash and sequence. A valid older checkpoint therefore cannot replace the referenced final checkpoint without breaking receipt binding.

Claims contain readable operational facts needed for audit: action kind, integer amount/currency, role, authorization result and reason. They do not contain access tokens, authorization headers, webhook signatures, payment instruments or private customer text. Sensitive source material is represented by stable references and canonical hashes.

## Limits

Tamper evidence detects mutation, deletion, insertion, reordering and substitution after commitment. It does not encrypt data, authenticate the original source, establish business authority, prove an external system told the truth, or prevent an authorized database administrator from deleting all copies. Retention, backups, access controls and authenticated adapters remain separate controls.
