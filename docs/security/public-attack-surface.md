# Public attack surface

| Endpoint | Class | Authentication | Mutation | Exposure |
|---|---|---|---|---|
| `/` | PUBLIC READ-ONLY DEMO | none | no | compiled UI only |
| `/health` | HEALTH | none | no | liveness; no dependency writes |
| `/v1/demo/stage11` | PUBLIC READ-ONLY DEMO | none | no | configured sanitized projection only |
| `/v1/demo/stage11/receipts/verify` | PUBLIC READ-ONLY PROOF | none | no | live verification or in-memory tamper copy |
| `/v1/pacts/{id}/status` | AUTHENTICATED AGENT READ | Runtime STS JWT | no | sanitized status |
| `/v1/pacts/{id}/chronicle` | AUTHENTICATED AGENT READ | Runtime STS JWT | no | authorized causal view |
| `/v1/pacts/{id}/observability` | AUTHENTICATED AGENT READ | Runtime STS JWT | no | sanitized proof fields |
| `/v1/pacts/{id}/actions/{refund,replacement,goodwill}` | AUTHENTICATED AGENT ACTION | Runtime STS JWT + role capability | yes | deterministic reservation before adapter |
| `/v1/pacts/{id}/resolution-plans` | AUTHENTICATED AGENT ACTION | Runtime STS JWT + Resolver capability | validation only | no execution/approval bypass |

CORS is same-origin by absence of permissive headers. Requests are capped at 1 MiB. CSP, frame denial, MIME sniffing denial, referrer and permissions policies are applied. API responses are `no-store`. Public demo data does not expose JWTs, webhook secrets, raw Firestore documents, approval internals, private memory, or raw model context.

