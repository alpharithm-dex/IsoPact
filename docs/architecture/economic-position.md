# Canonical economic position

All values are non-negative integer minor units in the pact's pinned currency. Binary floating point is forbidden; major-unit parsing rejects excess precision. Stage 6 supports USD commerce policy and rejects mixed/unsupported currency rather than silently converting it.

The reducer selects one current fact per `economic_object_id` using authoritative `source_version` followed by deterministic phase/time/ID tie-breaks. Thus pending → settled for one refund contributes $200, not $400; reversed or blocked objects do not remain active compensation. Event history is preserved outside the current projection.

Projected compensation includes proposed, pending, and settled primary outcomes plus authorized goodwill and other exceptions. Settled compensation contains only demonstrated settled facts. Goodwill is tracked independently from primary compensation even though it contributes to overall customer value. `projected_excess_exposure` is the canonical projected total above captured value; overlapping rule impacts are not added to it.

Partial refunds require distinct approved `semantic_intent_id` and `economic_scope` values, such as separate line/subclaim scopes. Equal amounts do not establish duplication. Reusing the same intent and scope does. This avoids the known false-merge risk while allowing `$50 + $50 + $100` against a $200 capture.

Protected Value is independently reduced from deduplicated typed events:

`invalid action prevented + authorized value recovered - legitimate value delayed`.

A pre-existing reversible replacement is only a `recoverable_candidate_value` in Stage 6. It remains recovered value $0 until later compensation succeeds and authoritative recovery evidence exists.
