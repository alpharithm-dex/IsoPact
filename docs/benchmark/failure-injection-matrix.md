# Stage 12 failure-injection matrix

The machine-readable 30-row matrix is `artifacts/benchmark/failure-injection.json`. Every row records injection point, expected and observed behavior, economic executions, integrity, and PASS/FAIL.

| Injection group | Expected and observed safety behavior |
|---|---|
| Firestore read/transaction/contention | fail closed or DEFER; no downstream authority |
| Lost response/restart/ack boundary | persist ambiguity; no duplicate economic execution |
| Pub/Sub duplicate/reorder/delay/restart | one logical evidence transition; no false settlement |
| Webhook forgery | no Rank 1 evidence or settlement |
| Gemini/Compiler/Resolver/Armor failures | no trusted-policy or execution-authority mutation |
| Memory poisoning | trusted policy remains pinned |
| KMS unavailable | settlement truth remains honest; no manufactured receipt |
| OTLP unavailable | business semantics unchanged |
| Token, identity, role, body spoofing | zero unauthorized consequential calls |
| Claim/receipt/checkpoint tampering | integrity verification fails |

Restart boundaries include reservation-before-call, external-call-before-result, OUTCOME_UNKNOWN persistence, evidence-before-ack, evidence-before-evaluation, compensation authority/call/confirmation, and settlement-before-signing. No unsafe duplicate was observed in the modeled matrix.

