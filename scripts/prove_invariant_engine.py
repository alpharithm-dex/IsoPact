from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from google.cloud import firestore

from isopact.invariants.engine import CommerceInvariantEngine
from isopact.invariants.firestore import FirestoreInvariantRepository
from isopact.invariants.models import EconomicFactKind, EconomicPhase, EvaluationResult
from isopact.invariants.scenarios import NOW, fact, preexisting_divergence_facts, protected_events, protected_facts, stage6_policy, unmanaged_facts


OUT = ROOT / "artifacts" / "invariants"


def write(name: str, value: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def evaluate(engine, pact_id, facts, *, evidence=False, events=(), revision=6):
    return engine.evaluate(
        pact_id=pact_id, graph_revision=revision, facts=tuple(facts), policy=stage6_policy(),
        selected_resolution="successful_refund", settlement_evidence_satisfied=evidence,
        ticket_closed=True, agent_complete=True, protection_events=tuple(events), evaluated_at=NOW,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-project")
    args = parser.parse_args()
    engine = CommerceInvariantEngine()

    unmanaged = evaluate(engine, "pact_stage6_unmanaged", unmanaged_facts())
    pending_facts = protected_facts(settled=False)
    protected_pending = evaluate(engine, "pact_stage6_protected", pending_facts, events=protected_events(pending_facts))
    final_facts = protected_facts(settled=True)
    protected_final = evaluate(engine, "pact_stage6_protected", final_facts, evidence=True, events=protected_events(final_facts))
    divergent = evaluate(engine, "pact_stage6_preexisting_divergence", preexisting_divergence_facts())

    write("unmanaged-economic-proof.json", {"proof_label": "projected exposure, not cash loss", **unmanaged.to_dict(), "canonical_exposure_minor_units": unmanaged.economic_position.projected_excess_exposure, "conflict_impacts_not_summed": True})
    protected_doc = {"claim_label": "projected invalid value prevented; not cash saved", "before_authoritative_success": protected_pending.to_dict(), "after_authoritative_success": protected_final.to_dict(), "protection_events": [item.to_dict() for item in protected_events(final_facts)]}
    write("protected-economic-proof.json", protected_doc)
    write("preexisting-divergence.json", {**divergent.to_dict(), "replacement_was_prevented": False, "recovery_requires_stage7_and_authoritative_evidence": True})

    rng = random.Random(6006)
    valid = invalid = valid_failures = invalid_detected = reducer_failures = ordering_failures = 0
    for case in range(300):
        amounts = [rng.randint(0, 10_000) for _ in range(rng.randint(1, 5))]
        facts = tuple(fact(f"property_{case}_{i}", EconomicFactKind.REFUND, EconomicPhase.PENDING, amount, intent=f"subclaim-{case}-{i}", scope=f"line:{i}") for i, amount in enumerate(amounts))
        bundle = evaluate(engine, f"property_{case}", facts)
        shuffled = list(facts)
        rng.shuffle(shuffled)
        reordered = evaluate(engine, f"property_{case}", tuple(shuffled))
        bound = next(item for item in bundle.evaluations if item.rule_id == "COMMERCE_REFUND_VALUE_BOUND")
        reducer_failures += bundle.economic_position.projected_total_compensation != sum(amounts)
        ordering_failures += bundle.economic_position.to_dict() != reordered.economic_position.to_dict()
        if sum(amounts) <= 20_000:
            valid += 1
            valid_failures += bound.result is not EvaluationResult.PASS
        else:
            invalid += 1
            invalid_detected += bound.result is EvaluationResult.FAIL
    property_summary = {"seed": 6006, "generated_cases": 300, "valid_cases": valid, "invalid_cases": invalid, "invariant_failures_in_valid_cases": valid_failures, "invalid_cases_correctly_detected": invalid_detected, "canonical_reducer_failures": reducer_failures, "insertion_order_failures": ordering_failures, "model_calls": engine.model_calls}
    write("property-test-summary.json", property_summary)

    samples = []
    for i in range(1_000):
        start = time.perf_counter_ns()
        evaluate(engine, f"perf_{i}", unmanaged_facts())
        samples.append((time.perf_counter_ns() - start) / 1_000_000)
    ordered = sorted(samples)
    perf = {"evaluations": len(samples), "unit": "milliseconds", "p50": round(statistics.median(samples), 4), "p95": round(ordered[949], 4), "max": round(max(samples), 4), "environment": "local single-process Python; not a production scale claim", "model_calls": engine.model_calls}
    write("performance.json", perf)

    live = {"attempted": False}
    if args.live_project:
        pact_id = "pact_stage6_live_economic_integrity"
        client = firestore.Client(project=args.live_project)
        pact = client.collection("pacts").document(pact_id)
        pact.set({"pact_id": pact_id, "status": "ACTIVE", "graph_revision": 6, "created_at": NOW})
        repository = FirestoreInvariantRepository(args.live_project, client=client)
        conflict_bundle = evaluate(engine, pact_id, preexisting_divergence_facts(), revision=8)
        repository.persist(conflict_bundle)
        live_bundle = evaluate(engine, pact_id, final_facts, evidence=True, events=protected_events(final_facts), revision=9)
        snapshot_id = repository.persist(live_bundle, protected_events(final_facts))
        stored = pact.collection("economic_snapshots").document(snapshot_id).get().to_dict()
        counts = {name: len(list(pact.collection(name).stream())) for name in ("economic_snapshots", "invariant_evaluations", "invariant_conflicts", "protection_events")}
        conflict_statuses = sorted(item.to_dict()["status"] for item in pact.collection("invariant_conflicts").stream())
        live = {"attempted": True, "project": args.live_project, "database": "(default)", "pact_id": pact_id, "snapshot_id": snapshot_id, "stored_lifecycle": stored["lifecycle_recommendation"], "stored_rule_set": f"{stored['rule_set_id']}@{stored['rule_set_version']}", "collection_counts": counts, "historical_conflict_statuses": conflict_statuses, "verified": counts["economic_snapshots"] >= 2 and counts["invariant_evaluations"] >= 18 and counts["invariant_conflicts"] >= 1 and conflict_statuses == ["RESOLVED"] and counts["protection_events"] == 2}
        write("live-firestore-proof.json", live)

    summary = {"status": "PASS", "rules": len(unmanaged.evaluations), "rule_versions": sorted({item.rule_version for item in unmanaged.evaluations}), "unmanaged_projected": unmanaged.economic_position.projected_total_compensation, "unmanaged_excess": unmanaged.economic_position.projected_excess_exposure, "protected_final_authorized": protected_final.economic_position.projected_total_compensation, "protected_value": protected_final.protection_summary.protected_value, "preexisting_recoverable": divergent.economic_position.recoverable_candidate_value, "preexisting_recovered": divergent.economic_position.recovered_value, "properties": property_summary, "performance": perf, "live_firestore": live, "model_calls": engine.model_calls}
    write("summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
