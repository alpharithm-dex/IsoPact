# ADR-006: Gemini Reasoning Is Not Authority

- Status: Accepted, implemented, and proven live on Vertex AI
- Date: 2026-08-23

## Context

Natural-language requests need interpretation, but model output is probabilistic and may be influenced by adversarial text. Consequential policy cannot be derived from that output.

## Decision

Gemini returns only strict `CandidateOutcomePact` data: candidate outcome classification, explicit subject references, requested resolution semantics, candidate concepts/evidence categories, ambiguities, and source grounding. Its Pydantic schema contains no policy ID/version, limits, approval threshold, permissions, invariant logic, settlement state, executable operation, or tool field.

`SemanticValidator` verifies model candidates against authoritative case context. `PolicyCatalog` supplies all trusted resolution paths, exclusivity, goodwill limit, evidence definitions, approval threshold, and duplicate-compensation behavior. Successful output is `ValidatedOutcomePactDraft` with `activation_state=DRAFT_NOT_ENFORCEABLE`; future activation is outside Stage 3.

The provider receives no tools. Prompt and ticket content are explicitly untrusted. A model outage, empty/malformed response, schema error, unknown classification, subject mismatch, or unsupported semantic returns `REJECTED` or `NEEDS_CLARIFICATION` with no trusted draft.

## Consequences

Structured generation improves syntax but does not prove semantic or policy validity. Model contribution and deterministic contribution remain separate in every result. The compiler can become unavailable without weakening Stage 1 reservation enforcement.
