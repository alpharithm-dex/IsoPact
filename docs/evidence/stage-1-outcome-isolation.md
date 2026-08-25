# Stage 1 Evidence: Application-Level Outcome Isolation

- Status: PASS
- Recorded: 2026-08-23
- Runtime: CPython 3.12.7 on Windows
- Scope: in-process deterministic domain core and concurrency-safe in-memory repository only

## Architecture tested

The test target is the framework-independent domain core in `src/isopact`: typed pact/intent/operation/reservation/slot/policy/decision/outcome models; deterministic economic canonicalization; repository protocol; per-pact-locking in-memory repository; reservation state machine; and authorization engine. There are no network, Firestore, Gemini/LLM, ADK, UI, SaaS mock, or Pub/Sub components in this stage.

Operation-key deduplication and resolution-slot exclusivity are independently exercised. The economic key excludes transport IDs and policy version. Each authorization pins its policy version separately, so publishing a new policy cannot bypass a live, unknown, or confirmed reservation.

## Exact command and result

```powershell
python -m unittest discover -s tests -v
```

```text
Ran 13 tests in 0.247s

OK
METRIC duplicate_refund_contenders=25 downstream_executions=1
METRIC ambiguous_state=OUTCOME_UNKNOWN second_attempt=DEFER downstream_executions=1
METRIC stress_iterations=100 invariant_violations=0 unknown_retry_violations=0
METRIC refund_replacement_contenders=2 winning_primary_resolutions=1
METRIC independent_pacts=20 observed_max_concurrent=20
```

Repeated-run check:

```powershell
$fail=0; 1..10 | ForEach-Object { python -m unittest discover -s tests 2>&1 | Out-Null; if($LASTEXITCODE -ne 0){$fail++} }; "repeated_runs=10 failures=$fail"
```

```text
repeated_runs=10 failures=0
```

Model-boundary and syntax checks:

```powershell
rg -n -i 'gemini|vertex|google[._ -]?adk|\bllm\b|openai|anthropic' src
python -m compileall -q src tests
```

```text
forbidden_model_references=0
compileall_exit=0
```

## Concurrency method and observations

- Duplicate race: 25 `ThreadPoolExecutor` workers synchronize on one `threading.Barrier`. Every intent uses different agent/request/session/trace metadata. The repository grants one `ALLOW`; a thread-safe counting downstream observes exactly one call.
- Exclusive-path race: refund and replacement synchronize on a two-party barrier. Their SHA-256 operation keys differ, but both request `primary_compensation`; exactly one is allowed and one receives `EXCLUSIVE_RESOLUTION_CONFLICT`.
- Executing retry: 10 equivalent retries synchronize while the first reservation is `EXECUTING`; all return `DEFER / OPERATION_IN_PROGRESS`.
- Independent pacts: 20 threads use distinct pact locks, then overlap a measured execution section. Observed maximum concurrent activity was 20, demonstrating that external work is not held behind one global repository lock.
- Stress: deterministic seed `8472`; 100 iterations, each with 2-12 barrier-synchronized, randomly scheduled refund/replacement contenders. Primary execution invariant violations: 0. Each iteration also verifies that an independent `OUTCOME_UNKNOWN` reservation makes an equivalent changed-request-ID retry defer; violations: 0.

These results prove behavior for one CPython process and this in-memory implementation. They do not claim distributed or Firestore concurrency guarantees.

## State and retry evidence

| Condition | Recorded state | Equivalent retry | Slot behavior |
|---|---|---|---|
| Execution active | `EXECUTING` | `DEFER / OPERATION_IN_PROGRESS` | Held |
| Authoritative success | `CONFIRMED` | `BLOCK / DUPLICATE_OPERATION` | Held |
| Authoritative proof write did not occur | `FAILED_AUTHORITATIVELY` | Explicit retry returns `ALLOW / AUTHORITATIVE_FAILURE_RETRY`; same operation key and incremented attempt | Released then reacquired |
| Lost response after downstream call | `OUTCOME_UNKNOWN` | `DEFER / EXTERNAL_OUTCOME_UNKNOWN` | Held |
| Later authoritative success after unknown | `CONFIRMED` | Blocked | Held |

`OUTCOME_UNKNOWN` is never treated as failure. Future authoritative evidence may transition it only to `CONFIRMED` or `FAILED_AUTHORITATIVELY`. Only the latter can permit retry.

## Failure-invariant result

- Duplicate consequential executions observed: 0.
- Two confirmed full refunds for one semantic operation: 0.
- Refund and replacement both obtaining primary authority: 0.
- Transport/agent metadata bypasses: 0.
- Policy-version bypasses: 0; old reservation retained the economic key.
- Ambiguous failure releases: 0.
- Stress invariant violations: 0.

## Limitations

- The in-memory repository is process-local and not durable; process crash recovery is not proven.
- Python thread tests exercise real synchronization and interleaving, but do not prove multi-process, distributed, Firestore, or cross-language behavior.
- The short lock registry uses a global lock only to create/retrieve per-pact locks; this is not the operation execution critical section. Extreme pact-creation throughput is not benchmarked.
- SHA-256 hash collision is not the meaningful risk; canonical-field false merge/separation remains a domain-model risk.
- `EXPIRED` exists in the lifecycle but no clock-driven expiry is implemented. Authority cannot expire after execution begins.
- Authoritative evidence authentication and persistence belong to later stages.
