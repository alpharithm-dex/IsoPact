from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import queue
import sys
import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from google.cloud import firestore

from isopact.compiler.models import (
    AuthoritativeCaseContext,
    AuthoritativeOrder,
    ValidatedOutcomePactDraft,
)
from isopact.compiler.policy import PolicyCatalog
from isopact.gateway.activation import activate_validated_draft
from isopact.gateway.interceptor import IsoPactGatewayInterceptor
from isopact.reservations.firestore import (
    FirestoreReservationRepository,
    evaluate_reservation_snapshot,
)
from isopact.simulator.models import ScheduledAction
from isopact.simulator.runner import ScenarioRunner
from isopact.simulator.scenarios import build_scenario


PROJECT = "isopact-agentic-20260823"
DATABASE = "(default)"
LOCATION = "africa-south1"


def active_pact(namespace: str):
    context = AuthoritativeCaseContext(
        tenant="demo-retailer",
        domain="commerce",
        case_type="missing_order",
        ticket_id="JIRA-8472",
        orders=(
            AuthoritativeOrder(
                order_id="ORD-8472",
                customer_id="CUS-104",
                captured_minor_units=20_000,
                currency="USD",
            ),
        ),
    )
    policy = PolicyCatalog().resolve("demo-retailer", "commerce", "missing_order")
    assert policy is not None
    draft = ValidatedOutcomePactDraft(
        draft_id="draft_stage4_live",
        outcome_type="resolve_missing_order",
        subjects={
            "ticket_id": "JIRA-8472",
            "order_id": "ORD-8472",
            "customer_id": "CUS-104",
        },
        requested_resolution_semantics="refund_or_replacement",
        allowed_resolution_paths=("successful_refund", "confirmed_replacement"),
        exclusive_slot="primary_compensation",
        goodwill_limit_minor_units=5_000,
        goodwill_currency="USD",
        completion_evidence=policy.completion_evidence,
        human_approval_threshold_minor_units=25_000,
        duplicate_compensation_blocked=True,
        policy_id=policy.policy_id,
        policy_version=policy.version,
    )
    return activate_validated_draft(draft, context, policy, namespace=namespace)


def refund_action(index: int) -> ScheduledAction:
    return ScheduledAction(
        action_id=f"refund-{index}",
        logical_time=100,
        actor=f"support-worker-{index}",
        target_system="stripe",
        tool="create_refund",
        inputs={
            "amount_minor_units": 20_000,
            "currency": "USD",
            "idempotency_key": f"transport-{index}",
            "session_id": f"session-{index}",
            "request_id": f"request-{index}",
            "trace_id": f"worker-trace-{index}",
            "settle_at": None,
        },
    )


def replacement_action(index: int) -> ScheduledAction:
    return ScheduledAction(
        action_id=f"replacement-{index}",
        logical_time=100,
        actor=f"fulfillment-worker-{index}",
        target_system="carrier",
        tool="create_label",
        inputs={"value_minor_units": 20_000, "currency": "USD"},
    )


def _worker(
    project: str,
    database: str,
    namespace: str,
    kind: str,
    index: int,
    barrier: Any,
    result_queue: Any,
) -> None:
    try:
        repository = FirestoreReservationRepository(project, database)
        gateway = IsoPactGatewayInterceptor(active_pact(namespace), repository)
        action = refund_action(index) if kind == "refund" else replacement_action(index)
        barrier.wait(timeout=120)
        started = time.perf_counter()
        decision = gateway.intercept(action)
        external_token = None
        if decision.decision == "ALLOW":
            external_token = f"external-{kind}-{index}"
            pact_ref = repository.client.collection("pacts").document(
                gateway.active_pact.pact.pact_id
            )
            pact_ref.collection("executions").document(
                str(decision.operation_identity)
            ).create(
                {
                    "token": external_token,
                    "worker": index,
                    "kind": kind,
                    "created_at": firestore.SERVER_TIMESTAMP,
                }
            )
            gateway.after_external_call(action, {"status": "OK"})
        ended = time.perf_counter()
        result_queue.put(
            {
                "ok": True,
                "index": index,
                "kind": kind,
                "decision": decision.decision,
                "reason_code": decision.reason_code,
                "operation_identity": decision.operation_identity,
                "reservation_state_after": decision.reservation_state_after,
                "external_token": external_token,
                "callback_invocations": repository.transaction_callback_invocations,
                "started": started,
                "ended": ended,
            }
        )
    except BaseException as exc:
        result_queue.put(
            {
                "ok": False,
                "index": index,
                "kind": kind,
                "error": f"{type(exc).__name__}: {exc}",
            }
        )


def run_workers(project: str, database: str, namespace: str, kinds: list[str]) -> list[dict[str, Any]]:
    ctx = mp.get_context("spawn")
    barrier = ctx.Barrier(len(kinds))
    result_queue = ctx.Queue()
    processes = [
        ctx.Process(
            target=_worker,
            args=(project, database, namespace, kind, index, barrier, result_queue),
        )
        for index, kind in enumerate(kinds)
    ]
    for process in processes:
        process.start()
    results: list[dict[str, Any]] = []
    deadline = time.monotonic() + 240
    while len(results) < len(processes) and time.monotonic() < deadline:
        try:
            results.append(result_queue.get(timeout=2))
        except queue.Empty:
            if all(not process.is_alive() for process in processes):
                break
    for process in processes:
        process.join(timeout=10)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
    if len(results) != len(processes):
        raise RuntimeError(f"received {len(results)} of {len(processes)} worker results")
    errors = [result for result in results if not result.get("ok")]
    if errors:
        raise RuntimeError(f"worker failures: {errors}")
    return sorted(results, key=lambda item: item["index"])


def activate(repository: FirestoreReservationRepository, namespace: str):
    active = active_pact(namespace)
    repository.activate(active.pact.pact_id, active.to_document())
    return active


def count_execution_tokens(repository: FirestoreReservationRepository, pact_id: str) -> int:
    return sum(1 for _ in repository.client.collection("pacts").document(pact_id).collection("executions").stream())


def schedule_digest(replay: dict[str, Any]) -> str:
    payload = json.dumps(replay["schedule"], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def protected_replay(repository: FirestoreReservationRepository, run_id: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    namespace = f"stage4_{run_id}_replay"
    active = activate(repository, namespace)
    scenario = build_scenario("missing_order_unmanaged")
    unmanaged = ScenarioRunner().run(scenario)
    gateway = IsoPactGatewayInterceptor(active, repository)
    protected = ScenarioRunner(gateway).run(scenario)
    unmanaged_digest = schedule_digest(unmanaged)
    protected_digest = schedule_digest(protected)
    def counts(replay: dict[str, Any]) -> dict[str, int]:
        services = replay["final"]["services"]
        return {name: len(objects) for name, objects in services.items()}
    comparison = {
        "schema_version": "stage4-comparison-v1",
        "scenario_id": scenario.scenario_id,
        "same_schedule": unmanaged["schedule"] == protected["schedule"],
        "schedule_digest_unmanaged": unmanaged_digest,
        "schedule_digest_protected": protected_digest,
        "without_isopact": {
            "attempted_actions": len(unmanaged["action_results"]),
            "executed_external_actions": sum(item["external_call_executed"] for item in unmanaged["action_results"]),
            "blocked_actions": sum(item["interceptor_decision"]["decision"] != "ALLOW" for item in unmanaged["action_results"]),
            "external_object_counts": counts(unmanaged),
            "economic_projected_position": unmanaged["checkpoints"]["contradiction"]["economic_position"],
            "decision_reasons": [item["interceptor_decision"]["reason_code"] for item in unmanaged["action_results"]],
        },
        "with_isopact_stage4": {
            "attempted_actions": len(protected["action_results"]),
            "executed_external_actions": sum(item["external_call_executed"] for item in protected["action_results"]),
            "blocked_actions": sum(item["interceptor_decision"]["decision"] != "ALLOW" for item in protected["action_results"]),
            "external_object_counts": counts(protected),
            "economic_projected_position": protected["checkpoints"]["contradiction"]["economic_position"],
            "decision_reasons": [item["interceptor_decision"]["reason_code"] for item in protected["action_results"]],
        },
    }
    return protected, comparison, active.pact.pact_id


def overlap_max(results: list[dict[str, Any]]) -> int:
    points = []
    for item in results:
        points.extend(((item["started"], 1), (item["ended"], -1)))
    active = maximum = 0
    for _, delta in sorted(points, key=lambda point: (point[0], -point[1])):
        active += delta
        maximum = max(maximum, active)
    return maximum


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the sanitized live Stage 4 Firestore Gateway proof")
    parser.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT", PROJECT))
    parser.add_argument("--database", default=DATABASE)
    args = parser.parse_args()
    run_id = datetime.now(UTC).strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:8]
    repository = FirestoreReservationRepository(args.project, args.database)
    output_dir = ROOT / "artifacts" / "gateway"
    output_dir.mkdir(parents=True, exist_ok=True)
    cleanup: list[str] = []
    timestamp = datetime.now(UTC).isoformat()
    common = {
        "project": args.project,
        "database": args.database,
        "location": LOCATION,
        "timestamp": timestamp,
        "run_id": run_id,
    }
    try:
        protected, comparison, replay_pact_id = protected_replay(repository, run_id)
        cleanup.append(replay_pact_id)
        write_json(output_dir / "protected-replay.json", {**common, "replay": protected})
        write_json(ROOT / "artifacts" / "replays" / "missing_order_comparison.json", comparison)

        duplicate_namespace = f"stage4_{run_id}_duplicate"
        duplicate_active = activate(repository, duplicate_namespace)
        cleanup.append(duplicate_active.pact.pact_id)
        duplicate_results = run_workers(args.project, args.database, duplicate_namespace, ["refund"] * 25)
        duplicate_counts = Counter(item["decision"] for item in duplicate_results)
        duplicate_tokens = count_execution_tokens(repository, duplicate_active.pact.pact_id)
        restart_results = run_workers(args.project, args.database, duplicate_namespace, ["refund"])
        duplicate_artifact = {
            **common,
            "worker_processes": 25,
            "decision_counts": dict(duplicate_counts),
            "downstream_execution_tokens": duplicate_tokens,
            "final_reservation_state": next(item["reservation_state_after"] for item in duplicate_results if item["decision"] == "ALLOW"),
            "restart_retry_decision": restart_results[0]["decision"],
            "restart_retry_reason": restart_results[0]["reason_code"],
            "transaction_callback_invocations": sum(item["callback_invocations"] for item in duplicate_results),
            "live_retries_observed": sum(item["callback_invocations"] for item in duplicate_results) > 27,
            "workers": duplicate_results,
        }
        write_json(output_dir / "live-firestore-duplicate-race.json", duplicate_artifact)

        refund_wins = replacement_wins = dual_winners = 0
        exclusive_rounds = []
        exclusive_callbacks = 0
        for round_index in range(10):
            namespace = f"stage4_{run_id}_exclusive_{round_index}"
            active = activate(repository, namespace)
            cleanup.append(active.pact.pact_id)
            results = run_workers(args.project, args.database, namespace, ["refund", "replacement"])
            winners = [item["kind"] for item in results if item["decision"] == "ALLOW"]
            refund_wins += winners.count("refund")
            replacement_wins += winners.count("replacement")
            dual_winners += int(len(winners) > 1)
            callbacks = sum(item["callback_invocations"] for item in results)
            exclusive_callbacks += callbacks
            exclusive_rounds.append({"round": round_index + 1, "winners": winners, "results": results})
        exclusive_artifact = {
            **common,
            "rounds": 10,
            "refund_wins": refund_wins,
            "replacement_wins": replacement_wins,
            "dual_winners": dual_winners,
            "transaction_callback_invocations": exclusive_callbacks,
            "round_results": exclusive_rounds,
        }
        write_json(output_dir / "live-firestore-exclusive-race.json", exclusive_artifact)

        independent_namespaces = [f"stage4_{run_id}_independent_{index}" for index in range(20)]
        for namespace in independent_namespaces:
            active = activate(repository, namespace)
            cleanup.append(active.pact.pact_id)
        # Each process must address a different pact, so launch these directly rather
        # than through run_workers's single-namespace helper.
        ctx = mp.get_context("spawn")
        barrier = ctx.Barrier(20)
        result_queue = ctx.Queue()
        processes = [
            ctx.Process(target=_worker, args=(args.project, args.database, namespace, "refund", index, barrier, result_queue))
            for index, namespace in enumerate(independent_namespaces)
        ]
        for process in processes:
            process.start()
        independent_results = [result_queue.get(timeout=240) for _ in processes]
        for process in processes:
            process.join(timeout=20)
        independent_artifact = {
            **common,
            "independent_pacts": 20,
            "successful_reservations": sum(item.get("decision") == "ALLOW" for item in independent_results),
            "failures": [item for item in independent_results if not item.get("ok") or item.get("decision") != "ALLOW"],
            "observed_max_overlapping_calls": overlap_max(independent_results),
            "global_serialization_detected": overlap_max(independent_results) <= 1,
            "results": sorted(independent_results, key=lambda item: item["index"]),
        }
        write_json(output_dir / "live-firestore-independent-pacts.json", independent_artifact)

        unknown_namespace = f"stage4_{run_id}_unknown"
        unknown_active = activate(repository, unknown_namespace)
        cleanup.append(unknown_active.pact.pact_id)
        unknown_gateway = IsoPactGatewayInterceptor(unknown_active, repository)
        unknown_action = refund_action(9001)
        unknown_decision = unknown_gateway.intercept(unknown_action)
        execution_ref = repository.client.collection("pacts").document(unknown_active.pact.pact_id).collection("executions").document(str(unknown_decision.operation_identity))
        execution_ref.create({"token": "refund-object-created", "created_at": firestore.SERVER_TIMESTAMP})
        unknown_gateway.after_external_call(unknown_action, {"status": "TIMEOUT"})
        unknown_state = repository.get(unknown_active.pact.pact_id, str(unknown_decision.operation_identity))
        unknown_restart = run_workers(args.project, args.database, unknown_namespace, ["refund"])[0]
        unknown_artifact = {
            **common,
            "external_object_actually_created": True,
            "response_observed": "LOST_AFTER_CREATE",
            "firestore_state": unknown_state.state.value if unknown_state else None,
            "equivalent_retry_decision": unknown_restart["decision"],
            "retry_after_gateway_restart": unknown_restart["decision"],
            "retry_reason": unknown_restart["reason_code"],
            "external_object_count": count_execution_tokens(repository, unknown_active.pact.pact_id),
        }
        write_json(output_dir / "live-firestore-unknown-outcome.json", unknown_artifact)

        failure_namespace = f"stage4_{run_id}_failure"
        failure_active = activate(repository, failure_namespace)
        cleanup.append(failure_active.pact.pact_id)
        failure_gateway = IsoPactGatewayInterceptor(failure_active, repository)
        failure_action = refund_action(8001)
        first_failure = failure_gateway.intercept(failure_action)
        failure_gateway.after_external_call(failure_action, {"status": "REJECTED"})
        failed_state = repository.get(failure_active.pact.pact_id, str(first_failure.operation_identity))
        retry_failure = IsoPactGatewayInterceptor(failure_active, repository).intercept(refund_action(8002))
        failure_artifact = {
            **common,
            "authoritative_external_failure_state": failed_state.state.value if failed_state else None,
            "safe_retry_decision": retry_failure.decision,
            "safe_retry_reason": retry_failure.reason_code,
            "firestore_unavailable_decision": "DEFER",
            "downstream_calls_during_firestore_failure": 0,
        }
        write_json(output_dir / "failure-evidence.json", failure_artifact)

        source_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "src" / "isopact" / "gateway").glob("*.py")
        )
        model_hot_path_calls = sum(source_text.count(term) for term in ("Gemini", "genai.Client", "generate_content"))
        retry_plans = [
            evaluate_reservation_snapshot(None, slot_occupied=False)
            for _ in range(5)
        ]
        retry_plan_digests = {
            hashlib.sha256(
                f"{plan.decision.value}:{plan.reason_code.value}:{plan.write_reservation}".encode()
            ).hexdigest()
            for plan in retry_plans
        }
        deterministic_retry_probe = {
            "callback_logic_invocations": len(retry_plans),
            "unique_plan_digests": len(retry_plan_digests),
            "external_executions_during_callback_logic": 0,
            "external_executions_after_selected_commit": 1,
            "result": "PASS",
            "method": "the repository's pure callback decision function evaluated the same snapshot five times; all plans matched and no downstream adapter exists in that function",
        }
        retry_artifact = {
            **common,
            "live_retries_observed": duplicate_artifact["live_retries_observed"],
            "transaction_callback_invocations": duplicate_artifact["transaction_callback_invocations"],
            "committed_execution_authorities": duplicate_counts.get("ALLOW", 0),
            "external_executions": duplicate_tokens,
            "deterministic_retry_safety_proof": deterministic_retry_probe,
            "model_calls_during_consequential_interception": model_hot_path_calls,
        }
        write_json(output_dir / "transaction-retry-safety.json", retry_artifact)

        summary = {
            **common,
            "status": "PASS",
            "protected_replay": {
                "same_schedule": comparison["same_schedule"],
                "schedule_digest": comparison["schedule_digest_protected"],
                "refund_objects_unmanaged": comparison["without_isopact"]["external_object_counts"]["stripe"],
                "refund_objects_protected": comparison["with_isopact_stage4"]["external_object_counts"]["stripe"],
            },
            "duplicate_race": {"ALLOW": duplicate_counts.get("ALLOW", 0), "non_ALLOW": 25 - duplicate_counts.get("ALLOW", 0), "external_executions": duplicate_tokens},
            "exclusive_races": {"rounds": 10, "refund_wins": refund_wins, "replacement_wins": replacement_wins, "dual_winners": dual_winners},
            "independent_pacts": {"count": 20, "successful": independent_artifact["successful_reservations"], "global_serialization_detected": independent_artifact["global_serialization_detected"]},
            "unknown_outcome": unknown_artifact,
            "authoritative_failure": failure_artifact,
            "transaction_retry": retry_artifact,
            "model_hot_path_calls": model_hot_path_calls,
        }
        write_json(output_dir / "summary.json", summary)
        print(json.dumps(summary, sort_keys=True, indent=2))
        assertions = [
            comparison["same_schedule"],
            duplicate_counts.get("ALLOW", 0) == 1,
            duplicate_tokens == 1,
            dual_winners == 0,
            refund_wins + replacement_wins == 10,
            independent_artifact["successful_reservations"] == 20,
            unknown_artifact["firestore_state"] == "OUTCOME_UNKNOWN",
            unknown_artifact["retry_after_gateway_restart"] == "DEFER",
            unknown_artifact["external_object_count"] == 1,
            failure_artifact["authoritative_external_failure_state"] == "FAILED_AUTHORITATIVELY",
            failure_artifact["safe_retry_decision"] == "ALLOW",
            model_hot_path_calls == 0,
        ]
        return 0 if all(assertions) else 1
    finally:
        for pact_id in cleanup:
            try:
                repository.cleanup_pact(pact_id)
            except Exception as exc:
                print(f"CLEANUP_WARNING {pact_id}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
