# Four-minute demo script

Target: 3:45–4:00. Do not substitute replay for live execution without displaying **VERIFIED REPLAY**.

## 0:00–0:30 — Problem

“A closed ticket is not a settled outcome. This customer’s $200 order never arrived. Support refunds $200, Fulfillment replaces $200, Retention adds $50, and another workflow refunds $200 again. Every agent looks locally successful; together they project $650—$450 too much.” Show **Agent Complete / Business Unsettled** and the unmanaged projection.

## 0:30–1:05 — Architecture and Google Cloud proof

Show the architecture diagram, then the Cloud Run revision and four Agent Runtime resources. “Gemini 3.5 Flash and ADK interpret intent across four specialized agents in `europe-west1`. Signed minimal action intent reaches the Outcome Gateway in `africa-south1`. Gemini proposes; deterministic logic authorizes. Agent Gateway is not in canonical traffic.”

## 1:05–2:15 — Live protected execution

Open **Protected Outcome**, reset, and play live. Narrate the first refund `ALLOW`, replacement `BLOCK`, and duplicate refund `BLOCK`. Pause when Support is `COMPLETE` but the business is `NOT SETTLED`. “IsoPact reserves authority by semantic operation and resolution slot, not transport request ID.”

## 2:15–2:45 — Evidence settles the business

Continue until authenticated Rank 1 Stripe evidence arrives. Show `SETTLED`, $200 refund + $50 goodwill, replacement blocked, duplicate blocked, and $400 projected invalid value prevented. “This is not cash saved; it is invalid projected value prevented in this scenario.”

## 2:45–3:15 — Provenance

Open the Settlement Receipt and click **VERIFY INTEGRITY**: `VERIFIED`. Run **TAMPER TEST**: `INVALID`. “The KMS signature proves integrity of recorded settlement history, not that a source told the truth. Source authenticity comes from authenticated adapters.”

## 3:15–3:40 — Failure safety

Open **Stale Plan** and show `PRECONDITION_FAILED`, cancellation calls `0`. Briefly show reconciliation and `OUTCOME_UNKNOWN`: uncertain execution is reconciled from authoritative evidence instead of blindly retried.

## 3:40–4:00 — Close

“In our frozen Stage 12 benchmark, IsoPact detected all benchmark contradictions with no duplicate consequential executions. It is not distributed ACID and not universal accuracy. It is outcome settlement infrastructure beneath the fleet.”
