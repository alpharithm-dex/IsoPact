# When every agent succeeds and the business still fails

*This article was created for the purposes of entering the All Things Agentic Hackathon.*

A customer reports a missing $200 order. The support agent refunds it. The fulfillment agent ships a replacement. The retention agent adds goodwill. Another retry issues the refund again. Each automation may be locally reasonable, yet their combined projected compensation is $650.

IsoPact starts from a simple distinction: agent completion is not business settlement. It introduces an Outcome Pact that describes the allowed combined obligation. Gemini 3.5 Flash helps compile intent and reason about constrained recovery, but deterministic rules own consequential authorization. Authenticated evidence—not an agent’s confidence—determines whether the business is settled.

The four-agent fleet runs with Google ADK in Gemini Enterprise Agent Runtime. Minimal signed intent crosses to a Cloud Run gateway, where Firestore transactions reserve semantic operations and exclusive resolution slots before external calls. Ambiguous responses become persistent `OUTCOME_UNKNOWN`; they are reconciled from authoritative evidence instead of retried blindly. Pub/Sub transports evidence, KMS signs provenance, and OpenTelemetry reconstructs causality.

In the protected demo, the first $200 refund is authorized, a $200 replacement and duplicate $200 refund are blocked, and $50 goodwill remains allowed. That is $250 authorized compensation and $400 of projected invalid value prevented—not a claim of cash saved.

The hardest lesson was that reliability claims must name their boundary. IsoPact is not cross-SaaS ACID, exactly-once infrastructure, or an immutable database. It provides application-level outcome isolation backed by semantic identity, ranked evidence, deterministic invariants, and tamper-evident receipts. The remaining production work—enterprise adapters, backup strategy, and same-pact contention hardening—is explicit rather than hidden.
