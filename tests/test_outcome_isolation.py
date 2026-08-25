from __future__ import annotations

import random
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from isopact.domain.canonical import canonicalize
from isopact.domain.models import (
    Decision,
    ExecutionOutcome,
    Money,
    OperationIntent,
    OutcomePact,
    PolicyVersion,
    ReasonCode,
    ReservationState,
)
from isopact.reservations.engine import ReservationEngine
from isopact.reservations.memory import InMemoryReservationRepository


POLICY_V1 = PolicyVersion("commerce-compensation", "1")
POLICY_V2 = PolicyVersion("commerce-compensation", "2")


def pact(pact_id: str = "pact_order_8472", policy: PolicyVersion = POLICY_V1) -> OutcomePact:
    return OutcomePact(
        pact_id=pact_id,
        transaction=Money.from_major("200.00", "usd"),
        allowed_resolution_paths=frozenset(
            {"successful_refund", "confirmed_replacement", "authorized_goodwill"}
        ),
        exclusive_slots={
            "primary_compensation": frozenset(
                {"successful_refund", "confirmed_replacement"}
            ),
            "goodwill": frozenset({"authorized_goodwill"}),
        },
        policy=policy,
    )


def intent(
    *,
    pact_id: str = "pact_order_8472",
    resolution_path: str = "successful_refund",
    event_type: str = "refund",
    amount: str = "200",
    resource: str | None = None,
    policy: PolicyVersion = POLICY_V1,
    suffix: str = "0",
) -> OperationIntent:
    return OperationIntent(
        pact_id=pact_id,
        resolution_path=resolution_path,
        event_type=event_type,
        subject_id="ord-8472",
        amount=None if resource else Money.from_major(amount, "USD"),
        resource=resource,
        policy=policy,
        agent_id=f"agent-{suffix}",
        request_id=f"request-{suffix}",
        session_id=f"session-{suffix}",
        trace_id=f"trace-{suffix}",
    )


class CountingDownstream:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.calls = 0

    def call(self) -> None:
        with self._lock:
            self.calls += 1


class OutcomeIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = InMemoryReservationRepository()
        self.engine = ReservationEngine(self.repository)

    def test_canonical_identity_excludes_transport_metadata_and_normalizes_money(self) -> None:
        first = canonicalize(intent(amount="200.00", suffix="A"), pact())
        second = canonicalize(intent(amount="200", suffix="B"), pact())
        partial = canonicalize(intent(amount="50", suffix="C"), pact())
        self.assertEqual(first.operation_key, second.operation_key)
        self.assertNotEqual(first.operation_key, partial.operation_key)

    def test_authorization_result_has_stable_audit_metadata(self) -> None:
        decision = self.engine.authorize(pact(), intent())
        self.assertEqual(decision.pact_id, "pact_order_8472")
        self.assertEqual(len(decision.operation_key), 64)
        self.assertEqual(decision.requested_resolution_slot, "primary_compensation")
        self.assertEqual(decision.reservation_state, ReservationState.RESERVED)
        self.assertEqual(decision.decision, Decision.ALLOW)
        self.assertEqual(decision.reason_code, ReasonCode.AUTHORITY_RESERVED)
        self.assertEqual(decision.policy_reference, POLICY_V1.reference)
        self.assertIsNone(decision.existing_conflicting_reservation)

    def test_25_concurrent_duplicate_refunds_only_one_executes(self) -> None:
        contenders = 25
        barrier = threading.Barrier(contenders)
        downstream = CountingDownstream()

        def compete(index: int):
            barrier.wait()
            decision = self.engine.authorize(pact(), intent(suffix=str(index)))
            if decision.decision is Decision.ALLOW:
                self.engine.begin_execution(decision)
                downstream.call()
                self.engine.record_outcome(decision, ExecutionOutcome.CONFIRMED)
            return decision

        with ThreadPoolExecutor(max_workers=contenders) as pool:
            decisions = list(pool.map(compete, range(contenders)))

        self.assertEqual(sum(d.decision is Decision.ALLOW for d in decisions), 1)
        self.assertEqual(downstream.calls, 1)
        self.assertTrue(
            all(
                d.reason_code
                in {ReasonCode.AUTHORITY_RESERVED, ReasonCode.OPERATION_IN_PROGRESS, ReasonCode.DUPLICATE_OPERATION}
                for d in decisions
            )
        )
        print("METRIC duplicate_refund_contenders=25 downstream_executions=1")

    def test_refund_and_replacement_have_distinct_keys_but_one_slot_winner(self) -> None:
        barrier = threading.Barrier(2)
        refund = intent(suffix="refund")
        replacement = intent(
            resolution_path="confirmed_replacement",
            event_type="replacement",
            resource="replacement:ORD-8472",
            suffix="replacement",
        )
        self.assertNotEqual(
            canonicalize(refund, pact()).operation_key,
            canonicalize(replacement, pact()).operation_key,
        )

        def compete(operation: OperationIntent):
            barrier.wait()
            return self.engine.authorize(pact(), operation)

        with ThreadPoolExecutor(max_workers=2) as pool:
            decisions = list(pool.map(compete, [refund, replacement]))
        self.assertEqual(sum(d.decision is Decision.ALLOW for d in decisions), 1)
        self.assertEqual(
            sum(d.reason_code is ReasonCode.EXCLUSIVE_RESOLUTION_CONFLICT for d in decisions), 1
        )
        print("METRIC refund_replacement_contenders=2 winning_primary_resolutions=1")

    def test_goodwill_uses_separate_slot(self) -> None:
        primary = self.engine.authorize(pact(), intent())
        goodwill = self.engine.authorize(
            pact(),
            intent(
                resolution_path="authorized_goodwill",
                event_type="goodwill_credit",
                amount="50",
                suffix="goodwill",
            ),
        )
        self.assertEqual(primary.decision, Decision.ALLOW)
        self.assertEqual(goodwill.decision, Decision.ALLOW)
        self.assertEqual(goodwill.requested_resolution_slot, "goodwill")

    def test_retry_after_confirmed_success_is_blocked(self) -> None:
        first = self.engine.authorize(pact(), intent(suffix="A"))
        self.engine.begin_execution(first)
        self.engine.record_outcome(first, ExecutionOutcome.CONFIRMED)
        retry = self.engine.authorize(pact(), intent(suffix="B"))
        self.assertEqual(retry.decision, Decision.BLOCK)
        self.assertEqual(retry.reason_code, ReasonCode.DUPLICATE_OPERATION)

    def test_authoritative_failure_releases_slot_and_allows_explicit_retry(self) -> None:
        first = self.engine.authorize(pact(), intent(suffix="A"))
        self.engine.begin_execution(first)
        self.engine.record_outcome(first, ExecutionOutcome.FAILED_AUTHORITATIVELY)
        retry = self.engine.authorize(pact(), intent(suffix="B"))
        self.assertEqual(retry.decision, Decision.ALLOW)
        self.assertEqual(retry.reason_code, ReasonCode.AUTHORITATIVE_FAILURE_RETRY)
        reservation = self.repository.get(retry.pact_id, retry.operation_key)
        self.assertEqual(reservation.attempt_count, 2)
        self.assertIn(ReservationState.FAILED_AUTHORITATIVELY, reservation.state_history)

    def test_ambiguous_post_call_failure_defers_retry(self) -> None:
        downstream = CountingDownstream()
        first = self.engine.authorize(pact(), intent(suffix="A"))
        self.engine.begin_execution(first)
        downstream.call()
        self.engine.record_outcome(first, ExecutionOutcome.OUTCOME_UNKNOWN)

        retry = self.engine.authorize(pact(), intent(suffix="B"))
        if retry.decision is Decision.ALLOW:
            downstream.call()
        self.assertEqual(retry.reservation_state, ReservationState.OUTCOME_UNKNOWN)
        self.assertEqual(retry.decision, Decision.DEFER)
        self.assertEqual(retry.reason_code, ReasonCode.EXTERNAL_OUTCOME_UNKNOWN)
        self.assertEqual(downstream.calls, 1)
        print(
            "METRIC ambiguous_state=OUTCOME_UNKNOWN second_attempt=DEFER "
            "downstream_executions=1"
        )

    def test_authoritative_reconciliation_of_unknown(self) -> None:
        first = self.engine.authorize(pact(), intent())
        self.engine.begin_execution(first)
        self.engine.record_outcome(first, ExecutionOutcome.OUTCOME_UNKNOWN)
        self.engine.reconcile_unknown(first, ExecutionOutcome.CONFIRMED)
        retry = self.engine.authorize(pact(), intent(suffix="retry"))
        self.assertEqual(retry.decision, Decision.BLOCK)

    def test_concurrent_retry_while_executing_does_not_call_downstream(self) -> None:
        first = self.engine.authorize(pact(), intent(suffix="first"))
        self.engine.begin_execution(first)
        barrier = threading.Barrier(10)

        def retry(index: int):
            barrier.wait()
            return self.engine.authorize(pact(), intent(suffix=f"retry-{index}"))

        with ThreadPoolExecutor(max_workers=10) as pool:
            decisions = list(pool.map(retry, range(10)))
        self.assertTrue(all(d.decision is Decision.DEFER for d in decisions))
        self.assertTrue(all(d.reason_code is ReasonCode.OPERATION_IN_PROGRESS for d in decisions))

    def test_policy_version_change_cannot_bypass_economic_identity(self) -> None:
        old_operation = canonicalize(intent(policy=POLICY_V1), pact(policy=POLICY_V1))
        new_operation = canonicalize(intent(policy=POLICY_V2), pact(policy=POLICY_V2))
        self.assertEqual(old_operation.operation_key, new_operation.operation_key)

        first = self.engine.authorize(pact(policy=POLICY_V1), intent(policy=POLICY_V1))
        self.engine.begin_execution(first)
        self.engine.record_outcome(first, ExecutionOutcome.CONFIRMED)
        retry = self.engine.authorize(
            pact(policy=POLICY_V2), intent(policy=POLICY_V2, suffix="new-policy")
        )
        self.assertEqual(retry.decision, Decision.BLOCK)
        self.assertEqual(retry.policy_reference, POLICY_V1.reference)

    def test_unrelated_pacts_execute_concurrently_without_global_execution_lock(self) -> None:
        count = 20
        barrier = threading.Barrier(count)
        active_lock = threading.Lock()
        active = 0
        max_active = 0

        def execute(index: int):
            nonlocal active, max_active
            pact_id = f"pact-{index}"
            current_pact = pact(pact_id)
            current_intent = replace(intent(suffix=str(index)), pact_id=pact_id)
            barrier.wait()
            decision = self.engine.authorize(current_pact, current_intent)
            self.engine.begin_execution(decision)
            with active_lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.01)
            with active_lock:
                active -= 1
            self.engine.record_outcome(decision, ExecutionOutcome.CONFIRMED)
            return decision

        with ThreadPoolExecutor(max_workers=count) as pool:
            decisions = list(pool.map(execute, range(count)))
        self.assertTrue(all(d.decision is Decision.ALLOW for d in decisions))
        self.assertGreater(max_active, 1)
        print(f"METRIC independent_pacts=20 observed_max_concurrent={max_active}")

    def test_randomized_stress_100_iterations(self) -> None:
        rng = random.Random(8472)
        violations = 0
        unknown_retry_violations = 0
        for iteration in range(100):
            repository = InMemoryReservationRepository()
            engine = ReservationEngine(repository)
            current_pact = pact(f"stress-{iteration}")
            contenders = []
            for index in range(rng.randint(2, 12)):
                if rng.choice([True, False]):
                    op = replace(intent(suffix=str(index)), pact_id=current_pact.pact_id)
                else:
                    op = replace(
                        intent(
                            resolution_path="confirmed_replacement",
                            event_type="replacement",
                            resource="replacement:ORD-8472",
                            suffix=str(index),
                        ),
                        pact_id=current_pact.pact_id,
                    )
                contenders.append(op)
            barrier = threading.Barrier(len(contenders))
            executed = 0
            executed_lock = threading.Lock()

            def compete(op: OperationIntent):
                nonlocal executed
                barrier.wait()
                time.sleep(rng.random() / 10000)
                decision = engine.authorize(current_pact, op)
                if decision.decision is Decision.ALLOW:
                    engine.begin_execution(decision)
                    with executed_lock:
                        executed += 1
                    engine.record_outcome(decision, ExecutionOutcome.CONFIRMED)
                return decision

            with ThreadPoolExecutor(max_workers=len(contenders)) as pool:
                decisions = list(pool.map(compete, contenders))
            if executed > 1:
                violations += 1
            # Separately exercise an ambiguous operation on an independent pact each
            # iteration; schedule noise above must not affect its fail-closed retry.
            unknown_pact = pact(f"unknown-{iteration}")
            unknown_intent = replace(intent(suffix="unknown"), pact_id=unknown_pact.pact_id)
            first = engine.authorize(unknown_pact, unknown_intent)
            engine.begin_execution(first)
            engine.record_outcome(first, ExecutionOutcome.OUTCOME_UNKNOWN)
            retry = engine.authorize(
                unknown_pact, replace(unknown_intent, request_id=f"retry-{iteration}")
            )
            if retry.decision is not Decision.DEFER:
                unknown_retry_violations += 1
        self.assertEqual(violations, 0)
        self.assertEqual(unknown_retry_violations, 0)
        print(
            "METRIC stress_iterations=100 invariant_violations=0 "
            "unknown_retry_violations=0"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
