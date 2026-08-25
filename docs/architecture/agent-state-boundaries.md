# Agent state boundaries

The stores have non-interchangeable authority:

| Store | Purpose | Business authority |
|---|---|---|
| ADK session state | Conversation and task continuity | None |
| Memory Bank | Optional longer-term context; not integrated in Stage 8 | None |
| Pact Graph | Authoritative case truth and lifecycle projection | Yes, through deterministic reducers |
| Firestore reservations | Consequential execution authority | Yes, through transactions |
| Trusted Policy | Limits, paths, evidence rules, approvals | Yes |
| Evidence pipeline | Ranked external reality | Yes, according to pinned policy |

An agent statement is Rank 4 interpretation. It can be retained for audit but cannot satisfy Rank 1 settlement evidence. A PENDING refund remains PENDING even if an agent says it is complete. Session IDs and trace IDs are audit/correlation fields; they do not participate in semantic operation identity and cannot create a second refund authority.

