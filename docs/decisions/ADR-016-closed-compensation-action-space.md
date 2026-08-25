# ADR-016: Closed compensation action space

## Status

Accepted for Stage 7.

## Decision

Gemini may select only IDs supplied from the trusted Compensation Registry. Candidate plans cannot contain executable parameters. Trusted code binds targets and arguments from graph entities. Unknown IDs, raw arguments, target substitution, authority/precondition mutation, approval bypass, and evidence deletion proposals are visibly rejected rather than sanitized.

Settled Stripe refunds have an explicit registry entry whose compensation action is `None` and authority is human review only. No automatic refund reversal exists.

## Consequences

Adding recovery capability requires reviewed registry code and tests. Resolver quality can affect which safe candidate is proposed, but cannot expand consequential authority.
