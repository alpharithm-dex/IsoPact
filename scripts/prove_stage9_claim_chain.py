from __future__ import annotations

import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from google.api_core.exceptions import Aborted
from google.cloud import firestore
from isopact.evidence.canonical import GENESIS_CLAIM_HASH, chain_claim, verify_claim_chain
from isopact.evidence.firestore import FirestorePactGraphRepository
from isopact.evidence.models import ClaimType, EvidenceRank, ImmediateState, StateClaim
from prove_agent_fleet import active_pact

PROJECT = "isopact-agentic-20260823"


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int((len(ordered) - 1) * p + .999999))], 3)


def make_claim(pact_id: str, index: int, amount: int = 20_000) -> StateClaim:
    return StateClaim(
        claim_id=f"claim_concurrent_{index:02d}", pact_id=pact_id,
        claim_type=ClaimType.SYSTEM_STATE, source_system="stage9-concurrency-worker",
        source_actor=f"worker-{index:02d}", subject="ORD-8472", external_object_id=None,
        operation_identity=f"op-audit-{index:02d}", resolution_path=None,
        immediate_state=ImmediateState.UNKNOWN, evidence_rank=EvidenceRank.UNVERIFIED_NATURAL_LANGUAGE,
        occurred_at=f"logical:{index:08d}", ingested_at=f"2026-08-24T03:10:{index:02d}Z",
        trace_id=f"trace-stage9-concurrent-{index:02d}",
        policy_references=("commerce_missing_order_v1@1",),
        rule_references=("commerce_missing_order_rules@1",),
        normalized_payload={"amount_minor_units": amount, "worker": index, "purpose": "claim-chain-concurrency-proof"},
    )


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    active = active_pact(f"stage9-chain-{stamp}")
    client = firestore.Client(project=PROJECT)
    repository = FirestorePactGraphRepository(PROJECT, client=client)
    repository.activate_graph(active, datetime.now(UTC).isoformat())

    def append(index: int) -> dict:
        started = time.perf_counter()
        retries = 0
        while True:
            try:
                created = repository.append_claim(make_claim(active.pact.pact_id, index))
                return {"worker": index, "created": created, "retries": retries, "latency_ms": round((time.perf_counter()-started)*1000, 3)}
            except (Aborted, ValueError) as exc:
                if isinstance(exc, ValueError) and "Failed to commit transaction" not in str(exc):
                    raise
                retries += 1
                if retries >= 15: raise
                time.sleep(.05 * retries)

    with ThreadPoolExecutor(max_workers=25) as pool:
        results = list(pool.map(append, range(1, 26)))
    claims = repository.claims_for_pact(active.pact.pact_id)
    verification = verify_claim_chain(claims)
    mutation_refused = False
    try:
        repository.append_claim(make_claim(active.pact.pact_id, 1, 30_000))
    except ValueError as exc:
        mutation_refused = str(exc) == "COMMITTED_CLAIM_SEMANTIC_MUTATION_REFUSED"

    hashing = []
    for index in range(1, 501):
        started = time.perf_counter()
        chain_claim(make_claim(active.pact.pact_id, (index % 25) + 1), index, GENESIS_CLAIM_HASH)
        hashing.append((time.perf_counter() - started) * 1000)
    append_latencies = [item["latency_ms"] for item in results]
    proof = {
        "generated_at": datetime.now(UTC).isoformat(), "project": PROJECT,
        "pact_id": active.pact.pact_id, "concurrent_append_workers": 25,
        "worker_results": results, "claims": claims,
        "sequence_numbers": [item["sequence_number"] for item in claims],
        "forks": 0 if verification["claim_chain_valid"] else None,
        "terminal_claim_hash": verification["terminal_claim_hash"],
        "chain_verification": verification,
        "semantic_mutation_refused": mutation_refused,
        "performance_ms": {
            "claim_hashing": {"samples": len(hashing), "p50": round(statistics.median(hashing), 3), "p95": percentile(hashing, .95)},
            "firestore_claim_append": {"samples": len(append_latencies), "p50": round(statistics.median(append_latencies), 3), "p95": percentile(append_latencies, .95)},
        },
    }
    output = ROOT / "artifacts" / "security" / "claim-chain-concurrency.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print(json.dumps({key: proof[key] for key in ("pact_id", "concurrent_append_workers", "sequence_numbers", "forks", "terminal_claim_hash", "chain_verification", "semantic_mutation_refused", "performance_ms")}, indent=2))
    return 0 if verification["claim_chain_valid"] and len(claims) == 25 and mutation_refused else 1


if __name__ == "__main__":
    raise SystemExit(main())
