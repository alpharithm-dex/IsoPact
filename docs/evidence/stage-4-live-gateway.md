# Stage 4 evidence — live Firestore Gateway

- Status: PASS
- Run: `20260823204536_81299571`
- Timestamp: `2026-08-23T20:45:38.545607+00:00`
- Project/database/location: `isopact-agentic-20260823` / `(default)` / `africa-south1`
- Database type: live Firestore Native (not emulator)

## Protected replay

The unmanaged and protected runs used the same seven-action `missing_order_unmanaged` schedule. Both
schedule digests are `6bfba8125f850027429efde5c03938cbe0327e9f67796c7870aeb1492db827e8`.

- First refund: ALLOW; one Stripe call; immediate Stripe object state PENDING.
- Replacement label: BLOCK / `EXCLUSIVE_RESOLUTION_CONFLICT`; zero carrier calls.
- Replacement stock: BLOCK / `EXCLUSIVE_RESOLUTION_CONFLICT`; zero warehouse reservations.
- Authorized $50 goodwill: ALLOW; one CRM call.
- Second semantic refund: BLOCK / `DUPLICATE_OPERATION`; no second Stripe call.
- Unmanaged refund objects: 2. Protected refund objects: 1.
- Jira closure remained allowed as the documented Stage 4 boundary.

## Distributed live results

- Duplicate race: 25 independent worker processes; 1 ALLOW; 24 non-ALLOW; 1 downstream execution token;
  final winner state CONFIRMED. A fresh-process retry was BLOCK.
- Exclusive races: 10 fresh pacts; refund wins 5; replacement wins 5; dual winners 0.
- Independent pacts: 20/20 reservations succeeded; observed overlapping calls exceeded one; no global
  serialization was detected or designed.
- Transaction callbacks: 35 invocations in the duplicate proof versus 27 invocations without retries;
  live retries were therefore observed. Committed authorities and external executions remained 1.
- Deterministic retry-safety probe: the reservation decision input was evaluated five times while the
  external execution token was emitted once, after selected commit.

## Failure and restart results

- Lost response after external object creation persisted `OUTCOME_UNKNOWN`.
- An equivalent retry from a new Gateway process returned `DEFER/EXTERNAL_OUTCOME_UNKNOWN`.
- External object count remained 1.
- A definitive rejection persisted `FAILED_AUTHORITATIVELY`; an explicit retry received
  `ALLOW/AUTHORITATIVE_FAILURE_RETRY`.
- Simulated Firestore unavailability returned DEFER and produced zero downstream calls.

## Model hot path

The Gateway package dependency/source scan found zero Gemini, `genai.Client`, or `generate_content`
calls. The protected replay reported zero model calls during consequential interception.

## Artifacts

- `artifacts/replays/missing_order_comparison.json`
- `artifacts/gateway/protected-replay.json`
- `artifacts/gateway/live-firestore-duplicate-race.json`
- `artifacts/gateway/live-firestore-exclusive-race.json`
- `artifacts/gateway/live-firestore-independent-pacts.json`
- `artifacts/gateway/live-firestore-unknown-outcome.json`
- `artifacts/gateway/failure-evidence.json`
- `artifacts/gateway/transaction-retry-safety.json`
- `artifacts/gateway/summary.json`

The script cleaned only its own run-scoped pact documents after capturing results. Artifacts contain
project and database identifiers but no credentials, tokens, or authorization codes.
