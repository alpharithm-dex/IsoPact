from __future__ import annotations

import random
import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from isopact.domain.models import Money
from isopact.evidence.models import Authenticity, Evidence, EvidenceRank, ImmediateState, PactLifecycle
from isopact.evidence.reducer import reduce_operation
from isopact.invariants.economics import EconomicReducer, ProtectionLedger
from isopact.invariants.engine import CommerceInvariantEngine, default_rule_catalog
from isopact.invariants.models import EconomicFactKind, EconomicPhase, EvaluationResult, ProtectionEventType
from isopact.invariants.scenarios import NOW, fact, preexisting_divergence_facts, protected_events, protected_facts, stage6_policy, unmanaged_facts


def evaluate(facts, *, evidence=False, events=(), policy=None, closed=False, complete=False):
    return CommerceInvariantEngine().evaluate(
        pact_id="pact_stage6", graph_revision=7, facts=tuple(facts),
        policy=policy or stage6_policy(), selected_resolution="successful_refund",
        settlement_evidence_satisfied=evidence, ticket_closed=closed,
        agent_complete=complete, protection_events=tuple(events), evaluated_at=NOW,
    )


def result(bundle, rule_id):
    return next(item for item in bundle.evaluations if item.rule_id == rule_id)


def evidence(state, sequence, event_id):
    return Evidence(
        evidence_id=event_id, pact_id="pact_stage6", source_system="stripe",
        source_event_id=event_id, evidence_type=f"stripe.refund.{state.value.lower()}",
        evidence_rank=EvidenceRank.AUTHORITATIVE_SETTLED_EVENT,
        authenticity=Authenticity.VERIFIED, subject="order_200",
        external_object_id="re_1", operation_identity="op_refund", operation_attempt=1,
        source_sequence=sequence, resolution_path="successful_refund", resolved_state=state,
        payload_hash=event_id, occurred_at=f"2026-08-23T20:00:{sequence:02d}Z",
        ingested_at=NOW, verification_mechanism="SIGNED_WEBHOOK", trace_id=event_id,
    )


class InvariantEngineTests(unittest.TestCase):
    def test_unmanaged_position_is_canonical_not_conflict_sum(self):
        bundle = evaluate(unmanaged_facts())
        self.assertEqual(bundle.economic_position.projected_total_compensation, 65_000)
        self.assertEqual(bundle.economic_position.settled_total_compensation, 5_000)
        self.assertEqual(bundle.economic_position.projected_excess_exposure, 45_000)
        self.assertGreaterEqual(len(bundle.conflicts), 3)
        self.assertEqual(bundle.lifecycle_recommendation, PactLifecycle.VIOLATED)

    def test_refund_bound_and_partial_refunds(self):
        parts = tuple(fact(f"r{i}", EconomicFactKind.REFUND, EconomicPhase.PENDING, amount, intent=f"approved-subclaim-{i}", scope=f"line:{i}") for i, amount in enumerate((5_000, 5_000, 10_000), 1))
        self.assertEqual(result(evaluate(parts), "COMMERCE_REFUND_VALUE_BOUND").result, EvaluationResult.PASS)
        overflow = parts + (fact("r4", EconomicFactKind.REFUND, EconomicPhase.PROPOSED, 100, intent="approved-subclaim-4", scope="line:4", executed=False),)
        check = result(evaluate(overflow), "COMMERCE_REFUND_VALUE_BOUND")
        self.assertEqual(check.result, EvaluationResult.FAIL)
        self.assertEqual(check.economic_amounts["excess"], 100)

    def test_partial_equal_amounts_are_not_false_merged(self):
        facts = (fact("a", EconomicFactKind.REFUND, EconomicPhase.PENDING, 5_000, intent="shipping", scope="shipping"), fact("b", EconomicFactKind.REFUND, EconomicPhase.PENDING, 5_000, intent="damage", scope="item-2"))
        self.assertEqual(result(evaluate(facts), "COMMERCE_DUPLICATE_COMPENSATION").result, EvaluationResult.PASS)

    def test_semantic_duplicate_and_pending_conflict(self):
        facts = (fact("a", EconomicFactKind.REFUND, EconomicPhase.PENDING, 20_000, intent="same", scope="full"), fact("b", EconomicFactKind.REFUND, EconomicPhase.PENDING, 20_000, intent="same", scope="full"))
        bundle = evaluate(facts)
        self.assertEqual(result(bundle, "COMMERCE_DUPLICATE_COMPENSATION").result, EvaluationResult.FAIL)
        self.assertEqual(result(bundle, "COMMERCE_PENDING_PRIMARY_CONFLICT").result, EvaluationResult.FAIL)

    def test_refund_replacement_and_preexisting_divergence(self):
        bundle = evaluate(preexisting_divergence_facts())
        self.assertEqual(result(bundle, "COMMERCE_PRIMARY_RESOLUTION_EXCLUSIVE").result, EvaluationResult.FAIL)
        self.assertEqual(bundle.lifecycle_recommendation, PactLifecycle.VIOLATED)
        self.assertEqual(bundle.economic_position.recoverable_candidate_value, 20_000)
        self.assertEqual(bundle.economic_position.recovered_value, 0)

    def test_goodwill_cumulative_boundaries(self):
        for values, expected in [((5_000,), EvaluationResult.PASS), ((5_001,), EvaluationResult.FAIL), ((2_500, 2_500), EvaluationResult.PASS), ((3_000, 3_000), EvaluationResult.FAIL)]:
            facts = tuple(fact(f"g{i}", EconomicFactKind.GOODWILL, EconomicPhase.SETTLED, value, intent=f"g{i}", scope=f"exception:{i}") for i, value in enumerate(values))
            self.assertEqual(result(evaluate(facts), "COMMERCE_GOODWILL_LIMIT").result, expected)

    def test_ticket_and_agent_claims_cannot_supply_evidence(self):
        pending = (fact("refund", EconomicFactKind.REFUND, EconomicPhase.PENDING, 20_000, intent="refund", scope="full"),)
        bundle = evaluate(pending, closed=True, complete=True)
        self.assertEqual(result(bundle, "COMMERCE_COMPLETION_REQUIRES_EVIDENCE").result, EvaluationResult.UNKNOWN)
        self.assertEqual(bundle.lifecycle_recommendation, PactLifecycle.PENDING)
        settled = (replace(pending[0], phase=EconomicPhase.SETTLED, fact_id="fact_refund_2_settled", source_version=2),)
        bundle = evaluate(settled, evidence=True, closed=True, complete=True)
        self.assertEqual(result(bundle, "COMMERCE_COMPLETION_REQUIRES_EVIDENCE").result, EvaluationResult.PASS)
        self.assertEqual(bundle.lifecycle_recommendation, PactLifecycle.SETTLED)

    def test_authoritative_failure_is_not_settlement(self):
        failed = (fact("refund", EconomicFactKind.REFUND, EconomicPhase.FAILED, 20_000, intent="refund", scope="full"),)
        bundle = evaluate(failed, evidence=False)
        self.assertEqual(bundle.economic_position.failed_primary_value, 20_000)
        self.assertNotEqual(bundle.lifecycle_recommendation, PactLifecycle.SETTLED)

    def test_same_rank_transition_and_stale_regression(self):
        current, _ = reduce_operation(None, evidence(ImmediateState.SUCCEEDED, 10, "evt_success"))
        current, changed = reduce_operation(current, evidence(ImmediateState.REVERSED, 11, "evt_reversed"))
        self.assertTrue(changed)
        self.assertEqual(current["state"], "REVERSED")
        current, changed = reduce_operation(current, evidence(ImmediateState.FAILED, 9, "evt_stale_failed"))
        self.assertFalse(changed)
        self.assertEqual(current["state"], "REVERSED")

    def test_success_cannot_transition_directly_to_failed(self):
        current, _ = reduce_operation(None, evidence(ImmediateState.SUCCEEDED, 10, "evt_success"))
        current, changed = reduce_operation(current, evidence(ImmediateState.FAILED, 11, "evt_invalid_failed"))
        self.assertFalse(changed)
        self.assertEqual(current["state"], "SUCCEEDED")

    def test_current_object_transition_does_not_double_count(self):
        pending = fact("refund", EconomicFactKind.REFUND, EconomicPhase.PENDING, 20_000, intent="refund", scope="full", version=1)
        settled = replace(pending, phase=EconomicPhase.SETTLED, fact_id="fact_refund_2_settled", source_version=2)
        position, _, _ = EconomicReducer.reduce((pending, settled), stage6_policy())
        self.assertEqual(position.projected_total_compensation, 20_000)
        self.assertEqual(position.settled_total_compensation, 20_000)

    def test_protection_events_are_deduped_and_false_blocks_subtract(self):
        facts = protected_facts(settled=False)
        events = protected_events(facts)
        duplicate = events[0]
        delayed = ProtectionLedger.event(ProtectionEventType.LEGITIMATE_VALUE_DELAYED, fact("valid_partial", EconomicFactKind.REFUND, EconomicPhase.BLOCKED, 5_000, intent="valid", scope="line:1", executed=False), "FALSE_BLOCK", NOW)
        bundle = evaluate(facts, events=events + (duplicate, delayed))
        self.assertEqual(bundle.protection_summary.unique_event_count, 3)
        self.assertEqual(bundle.protection_summary.protected_value, 35_000)

    def test_protected_path_pending_then_settled(self):
        pending_facts = protected_facts(settled=False)
        pending = evaluate(pending_facts, events=protected_events(pending_facts))
        self.assertEqual(pending.lifecycle_recommendation, PactLifecycle.PENDING)
        final_facts = protected_facts(settled=True)
        final = evaluate(final_facts, evidence=True, events=protected_events(final_facts))
        self.assertEqual(final.economic_position.projected_total_compensation, 25_000)
        self.assertEqual(final.economic_position.projected_excess_exposure, 5_000)
        self.assertEqual(final.protection_summary.protected_value, 40_000)
        self.assertEqual(final.lifecycle_recommendation, PactLifecycle.SETTLED)

    def test_rule_versions_are_pinned_and_immutable(self):
        catalog = default_rule_catalog()
        pinned = catalog.resolve("commerce_missing_order_rules", "1")
        self.assertTrue(all(item.rule_version == "1.0.0" for item in pinned.rules))
        with self.assertRaises(ValueError):
            catalog.register(pinned)
        newer = catalog.resolve("commerce_missing_order_rules", "2")
        self.assertTrue(all(item.rule_version == "2.0.0" for item in newer.rules))
        historical = evaluate((), policy=stage6_policy(rule_version="1"))
        self.assertTrue(all(item.rule_version == "1.0.0" for item in historical.evaluations))

    def test_insertion_order_independence(self):
        facts = list(unmanaged_facts())
        expected = evaluate(facts).economic_position.to_dict()
        random.Random(612).shuffle(facts)
        self.assertEqual(evaluate(facts).economic_position.to_dict(), expected)

    def test_safe_money_boundaries(self):
        for value in (0, 1, 4_999, 5_000, 5_001, 19_999, 20_000, 20_001):
            self.assertEqual(Money("usd", value).minor_units, value)
        with self.assertRaises(ValueError): Money("USD", -1)
        with self.assertRaises(ValueError): Money.from_major("1.001", "USD")
        with self.assertRaises(ValueError): replace(stage6_policy(), currency="EUR")

    def test_300_generated_cases_obey_bound_property(self):
        rng = random.Random(6006)
        valid_failures = invalid_detected = 0
        for case in range(300):
            values = [rng.randint(0, 10_000) for _ in range(rng.randint(1, 5))]
            facts = tuple(fact(f"case{case}_{i}", EconomicFactKind.REFUND, EconomicPhase.PENDING, value, intent=f"case{case}_{i}", scope=f"subclaim:{i}") for i, value in enumerate(values))
            bundle = evaluate(facts)
            actual = result(bundle, "COMMERCE_REFUND_VALUE_BOUND").result
            self.assertEqual(bundle.economic_position.projected_total_compensation, sum(values))
            shuffled = list(facts)
            rng.shuffle(shuffled)
            self.assertEqual(evaluate(shuffled).economic_position.to_dict(), bundle.economic_position.to_dict())
            if sum(values) <= 20_000:
                valid_failures += actual is not EvaluationResult.PASS
            else:
                invalid_detected += actual is EvaluationResult.FAIL
        self.assertEqual(valid_failures, 0)
        self.assertGreater(invalid_detected, 0)


if __name__ == "__main__":
    unittest.main()
