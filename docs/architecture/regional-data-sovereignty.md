# Regional data sovereignty

The reasoning plane runs on Agent Runtime in `europe-west1`. The settlement and
data plane runs in `africa-south1`: Cloud Run owns deterministic authorization
and Firestore owns reservations, the raw Pact Graph, claims, evidence, and
settlement proofs.

Only minimal structured action context crosses regions: pact ID, the necessary
order/customer subject, amount when applicable, and session/trace/request IDs.
The managed identity token also crosses as the authentication envelope. Raw
customer records, the unrestricted Pact Graph, Firestore credentials, policy
mutation capability, and settlement state are not replicated to the agents.

The eight-request functional sample measured 573.217 ms p50 and 1,780.447 ms
p95 for Runtime-to-Outcome-Gateway HTTP round trips. Deterministic Gateway plus
Firestore authorization measured 63.719 ms p50 and 748.054 ms p95. Full Gateway
server action time measured 179.157 ms p50 and 1,377.865 ms p95. This is demo
responsiveness evidence, not a production throughput benchmark.

Evidence: `artifacts/agents/stage8b-data-sovereignty.json` and
`stage8b-latency.json`.
