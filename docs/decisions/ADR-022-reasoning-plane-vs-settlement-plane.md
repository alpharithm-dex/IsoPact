# ADR-022: Reasoning plane versus settlement plane

Status: Accepted

## Decision

Keep ADK/model reasoning in `europe-west1`, where managed Agent Runtime is
supported, and keep consequential reservation, external execution, Pact Graph,
and settlement in `africa-south1`, colocated with authoritative Firestore.

## Consequences

The design incurs a measurable cross-region HTTP cost but avoids moving raw
authoritative financial state merely to colocate it with a model. Agents express
intent; the settlement plane independently authenticates, authorizes, reserves,
executes, and evaluates evidence. An agent statement remains Rank 4 and cannot
commit settlement. Failure of the model or Runtime cannot weaken deterministic
authority.

