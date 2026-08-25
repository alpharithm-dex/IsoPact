# Devpost draft

## Project name

IsoPact

## Tagline

Outcome settlement infrastructure that keeps independent enterprise agents from succeeding locally while the business fails globally.

## Category

Fortified Enterprise Fleet

## Inspiration

The operational teams who inherit autonomous-agent decisions face a question agent dashboards do not answer: did the business actually settle correctly after every agent said it was done? A $200 missing order can trigger a refund, replacement, goodwill, and duplicate retry—four locally plausible actions projecting $650 in combined compensation.

## The problem

Agent completion is not business settlement. Independent agents optimize legitimate local goals, but gateways, workflow engines, provider idempotency keys, and model guardrails do not by themselves govern the combined enterprise obligation across payment, fulfillment, carrier, CRM, and support systems.

## What IsoPact does

IsoPact introduces an application-level Outcome Pact beneath the fleet. It reserves semantic operations and exclusive remedy slots, constrains compensation, ranks evidence by authority, persists ambiguous execution as `OUTCOME_UNKNOWN`, revalidates stale recovery plans, and issues tamper-evident settlement receipts.

In the canonical protected scenario, IsoPact authorizes a $200 refund and $50 goodwill while blocking a $200 replacement and duplicate $200 refund: $250 authorized compensation and $400 of projected invalid value prevented.

## Why multi-agent systems need it

Support, Fulfillment, Retention, and the Settlement Resolver are separately deployed agents with distinct identities, tools, and valid objectives. A monolithic orchestrator would hide the real enterprise boundary. IsoPact coordinates their shared obligation without centralizing all reasoning or giving any model settlement authority.

## How it works

Gemini 3.5 Flash and Google ADK interpret intent and propose constrained recovery in Gemini Enterprise Agent Runtime. Managed Agent Identity authenticates runtime actors. Memory Bank supplies non-authoritative context; Model Armor screens model-facing untrusted input.

The Cloud Run Outcome Gateway authenticates signed minimal intent, reserves authority in Firestore, applies capability and economic invariants, and only then calls enterprise adapters. Pub/Sub transports ranked evidence. Authenticated source evidence—not agent statements—settles the Pact Graph. KMS signs checkpoints and receipts; OpenTelemetry provides causal traces, logs, and metrics but never participates in authority.

## Demo

The live UI compares unmanaged $650 projected compensation with the protected result. It shows a real `BLOCK`, Agent `COMPLETE` while Business `NOT SETTLED`, Rank 1 evidence causing `SETTLED`, a verified signed receipt, tamper rejection, reconciliation, and a TOCTOU-safe stale-plan refusal.

Hosted project: https://isopact-outcome-gateway-442539309409.africa-south1.run.app/

## Architecture

Four Runtime agents and Gemini reasoning run in `europe-west1`; deterministic settlement, Firestore, Pub/Sub, adapters, and KMS run in `africa-south1`. Agent Gateway was provisioned but is default-deny and not bound to canonical traffic. A2A is not used in the canonical production flow.

## Google Cloud / Gemini stack

Gemini 3.5 Flash, Vertex AI, Google ADK, `google-genai`, Gemini Enterprise Agent Runtime, Agent Identity, Agent Registry, Memory Bank, Model Armor, Cloud Run, Firestore, Pub/Sub, Cloud KMS, Secret Manager, Cloud Trace, Cloud Logging, Cloud Monitoring, OpenTelemetry, React, TypeScript, and Python.

## Safety and governance

Deterministic logic owns consequential authorization. Gemini cannot authorize refunds or invent compensation types. Closed registries, role capabilities, human approval, and TOCTOU checks constrain recovery. Semantic duplicate prevention is scoped to modeled operation identity. Firestore claim history is append-oriented and hash-chained with KMS checkpoints, making tampering detectable; Firestore itself is not immutable.

## Benchmark results

In our frozen Stage 12 benchmark: 130 deterministic cases, 39 held-out cases, 2,500 generated property cases, and 30 injected failures. Contradiction recall and precision were 100% (95% Wilson CI 94.34%–100%); false-block rate was 0% (CI 0%–5.50%). There were zero duplicate consequential executions, unsupported closures, or unsafe automatic compensations in that benchmark. This is not universal accuracy or a production throughput result. Reconciliation success used only five eligible cases.

## What we learned

Reliable agent fleets need a boundary between reasoning and authority, semantic identity rather than transport identity, and evidence stronger than agent confidence. Ambiguity must become durable state, not an excuse to retry.

## Known limitations

The Compensation Registry is commerce-specific; Firestore lacks storage-level immutability, PITR, and delete protection; extreme same-pact writes contend on the provenance head; Agent Gateway is not canonical; A2A is not in production; the benchmark is bounded; and real customers require enterprise-specific authenticated adapters.

## What's next

Validated customer-specific adapters, backup/PITR hardening, provenance-head scalability, and controlled binding of additional platform networking only after its safety policy is fully proven.

## Testing instructions (<3 minutes)

1. Open the hosted URL and choose **Protected Outcome**.
2. Press Reset, then Play.
3. Observe refund `ALLOW`, replacement `BLOCK`, and duplicate refund `BLOCK`.
4. Observe Agent `COMPLETE` / Business `NOT SETTLED`.
5. Continue until Rank 1 evidence changes the pact to `SETTLED`.
6. Open Settlement Receipt and click **VERIFY INTEGRITY**: expect `VERIFIED`.
7. Optional **TAMPER TEST**: expect `INVALID`.
8. Open **Stale Plan**: expect `PRECONDITION_FAILED` and cancellation calls `0`.

## User-confirmation fields

- Submitter type: **NEEDS_USER_CONFIRMATION**
- Country: **NEEDS_USER_CONFIRMATION**
- Organization name / N/A behavior: **NEEDS_USER_CONFIRMATION**
- Exact project start date: **NEEDS_USER_CONFIRMATION**
- Final repository URL: https://github.com/alpharithm-dex/IsoPact
- Startup Prize eligibility: **NEEDS_USER_CONFIRMATION**
- Corporate email: **NEEDS_USER_CONFIRMATION**
- Final video URL: **NEEDS_USER_CONFIRMATION**
