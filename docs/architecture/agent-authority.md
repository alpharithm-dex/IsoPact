# Agent authority

Agent identity is enforced twice: Google supplies a distinct managed runtime identity, and IsoPact maps that resource to an immutable logical `AgentIdentity` and role. `AgentCapabilityPolicy` authorizes capabilities before a typed adapter reaches the Gateway. Its decisions use no model calls.

| Capability | Support | Fulfillment | Retention | Resolver |
|---|---:|---:|---:|---:|
| Read pact | Y | Y | Y | Y |
| Request refund | Y | N | N | N |
| Request replacement | N | Y | N | N |
| Request goodwill | N | N | Y | N |
| Read conflicts / request validated plan | N | N | N | Y |
| Edit policy | N | N | N | N |

The model-visible functions contain no Stripe, carrier, CRM, warehouse, Firestore transaction, policy-edit, approval-decision, or raw compensation executor. Consequential local adapters call `IsoPactGatewayInterceptor` first and call the simulator only after `ALLOW`. The deployed functions return authenticated control-plane request envelopes and do not pretend that envelope creation is external execution or settlement.

Resolver sees registry IDs and deterministic conflict summaries only. Candidate validation, execution-time preconditions, approval scope, idempotency, evidence qualification, and lifecycle remain Stage 7 code paths. Agent-generated approval prose has no representable approval credential.

