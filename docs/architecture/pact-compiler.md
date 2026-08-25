# Outcome Pact Compiler

## Safety boundary

```text
untrusted request + authoritative identifier context
  -> Gemini provider (structured CandidateOutcomePact, no tools)
  -> Pydantic schema validation
  -> deterministic semantic validator
  -> trusted tenant/domain/case mapping
  -> PolicyCatalog enrichment
  -> ValidatedOutcomePactDraft (not enforceable)
```

Gemini interprets; deterministic code validates and enriches. No compilation result authorizes a value-changing action or sets a pact lifecycle state.

## Candidate schema

`CandidateOutcomePact` contains candidate outcome type; grounded subject references; resolution semantics and concepts; suspected exclusivity; evidence concepts; explicit user constraints; ambiguity strings; source grounding; and optional extracted amount. It deliberately excludes policy and execution authority.

The Vertex provider uses `google-genai`, `genai.Client(vertexai=True, project=..., location=...)`, the stable `v1` API, `response_mime_type="application/json"`, and `response_schema=CandidateOutcomePact`. The model is configuration-driven through `GEMINI_MODEL`; `gemini-3.5-flash` was verified live in the dedicated project on 2026-08-23. The provider config contains `tools=None`.

Google's current SDK documentation supports Pydantic response schemas and Vertex client configuration. Implementation references:

- https://googleapis.github.io/python-genai/index.html
- https://cloud.google.com/vertex-ai/generative-ai/docs/sdks/overview

## Deterministic validation

Validation checks policy mapping, known outcome type, explicit subject existence and ownership, resolution concepts, exclusive “both required” conflicts, evidence concepts, currency, amount versus captured transaction, ambiguity, and provenance. Schema-valid malicious candidates remain untrusted and are rejected semantically.

`PolicyCatalog` maps `demo-retailer/commerce/missing_order` to `commerce_missing_order_v1@1`. It alone supplies allowed paths, `primary_compensation`, goodwill `$50 USD`, authoritative evidence types, `$250` approval threshold, and duplicate-compensation behavior.

## Providers and provenance

`GeminiPactCompilerProvider` labels output `google-vertex-ai/LIVE`; `DeterministicFixtureCompilerProvider` labels it `deterministic-fixture/FIXTURE`. The labels are closed literals and cannot be silently confused. `CompilationResult` stores the candidate/model metadata separately from the deterministic validation and trusted draft.

## Live proof configuration

No API key is accepted by the proof command. It requires Application Default Credentials and:

```powershell
$env:GOOGLE_CLOUD_PROJECT = "your-project"
$env:GOOGLE_CLOUD_LOCATION = "global"
$env:GEMINI_MODEL = "verified-eligible-model-id"
.\.venv-win\Scripts\python.exe scripts\prove_pact_compiler.py --runs 1
```

The script writes `artifacts/compiler/live-missing-order.json` only after at least one response is labeled live, schema-valid, and deterministically valid. Failed authentication/model calls produce no success artifact. Up to five runs can measure semantic agreement without claiming model determinism.

## Live environment proof

The dedicated project `isopact-agentic-20260823` has billing and `aiplatform.googleapis.com` enabled. ADC is configured with that quota project. A five-call `gemini-3.5-flash` run produced five schema-valid, deterministically valid candidates with one semantic signature. Sanitized output is stored in `artifacts/compiler/live-missing-order.json`; credentials and tokens are not stored in the repository.
