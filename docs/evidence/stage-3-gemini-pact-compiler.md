# Stage 3 Evidence: Gemini Outcome Pact Compiler

- Status: PASS
- Recorded: 2026-08-23
- Live project: `isopact-agentic-20260823`
- Live provider/model: `google-vertex-ai` / `gemini-3.5-flash`

## Implemented and tested offline

The current Google Gen AI SDK (`google-genai 1.75.0`) and Pydantic (`2.13.4`) are installed in the ignored `.venv-win` environment. The provider uses native structured output with `application/json` and `response_schema=CandidateOutcomePact`, Vertex AI mode, stable `v1`, ADC, configuration-driven project/location/model, and no tools.

```powershell
.\.venv-win\Scripts\python.exe -m unittest discover -s tests -v
```

```text
Ran 34 tests in 0.340s
OK
METRIC prompt_injection_cases=4 policy_mutations_accepted=0 consequential_tool_calls=0
```

The 34 tests include 13 Stage 1, 10 Stage 2, and 11 Stage 3 tests. Stage 3 covers valid compilation, subject grounding, policy enrichment, ambiguity, unknown/mismatched subject, unknown classification/mapping, provider outage, malformed response, five schema-valid semantic attacks, invented policy field schema rejection, four prompt injections, trusted limits/evidence, and absence of model tool authority.

## Live proof

Environment configuration completed:

```text
project=isopact-agentic-20260823
billingEnabled=true
aiplatform.googleapis.com=enabled
adc_available=true
quota_project=isopact-agentic-20260823
location=global
model=gemini-3.5-flash
```

```powershell
.\.venv-win\Scripts\python.exe scripts\prove_pact_compiler.py --runs 5
```

```text
stability_proof_exit=0
live_calls=5
successful_valid_calls=5
unique_semantic_signatures=1
validation_statuses=VALID,VALID,VALID,VALID,VALID
latencies_ms=13350,13529,13876,12923,11849
```

The sanitized structured artifact contains no credential, access token, sensitive header, or API key:

```text
artifacts/compiler/live-missing-order.json
SHA-256 BA1D8C14F0963139E10F3F36162046A1C96FBE1005A591E48A346F77AEC885F6
```

All live candidates identified `resolve_missing_order`, the authoritative subjects, refund/replacement concepts, `refund_or_replacement` semantics, and supported evidence categories. Deterministic validation supplied every trusted policy value.

## Adversarial result

- Four prompt-injection strings caused zero trusted policy changes and zero consequential tool calls.
- Schema-valid attacks covering unknown path, invented evidence, mandatory exclusive dual resolution, wrong amount, and unsupported currency all produced `REJECTED` with no draft.
- An invented `policy_id` field fails strict candidate schema validation.
- A different-customer subject fails authoritative ownership validation.
- Provider timeout/retry exhaustion and malformed response produce `REJECTED / MODEL_PROVIDER_UNAVAILABLE_OR_INVALID`, no model contribution, and no trusted draft.

## Primary live result

Gemini inferred `resolve_missing_order`, `ORD-8472`, `CUS-104`, `JIRA-8472`, refund/replacement concepts, and candidate refund/shipment evidence categories. Deterministic enrichment supplied `commerce_missing_order_v1@1`, `successful_refund`, `confirmed_replacement`, `primary_compensation`, goodwill limit `5000 USD` minor units, evidence `stripe.refund.succeeded` / `carrier.shipment.accepted`, approval threshold `25000` minor units, and `DRAFT_NOT_ENFORCEABLE`.

## Gate result

Gate 3 passes: genuine Vertex calls, native structured output, deterministic semantic validation, policy separation, adversarial/failure proofs, sanitized artifact, and Stage 1–2 regressions are all evidenced. Model semantic agreement is an observed 5/5 for this sample, not a general determinism claim.
