from __future__ import annotations

import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from isopact.agents.authority import AgentCapabilityDenied, AgentCapabilityPolicy
from isopact.agents.fleet import IDENTITIES, build_adk_fleet
from isopact.agents.models import AgentRole, AgentSessionContext, Capability
from isopact.agents.runtime import AgentToolRuntime
from isopact.compiler.models import AuthoritativeCaseContext, AuthoritativeOrder, ValidatedOutcomePactDraft
from isopact.compiler.policy import PolicyCatalog
from isopact.evidence.models import PactLifecycle
from isopact.evidence.reducer import evaluate_graph
from isopact.gateway.activation import activate_validated_draft
from isopact.gateway.interceptor import IsoPactGatewayInterceptor
from isopact.reservations.memory import InMemoryReservationRepository
from isopact.simulator.clock import VirtualClock
from isopact.simulator.ledger import EconomicLedger
from isopact.simulator.services import CarrierService, CrmService, JiraService, StripeService, WarehouseService


def active_pact(namespace="agents"):
    context=AuthoritativeCaseContext(tenant="demo-retailer",domain="commerce",case_type="missing_order",ticket_id="JIRA-8472",orders=(AuthoritativeOrder(order_id="ORD-8472",customer_id="CUS-104",captured_minor_units=20_000,currency="USD"),))
    policy=PolicyCatalog().resolve("demo-retailer","commerce","missing_order"); assert policy
    draft=ValidatedOutcomePactDraft(draft_id="draft_agents",outcome_type="resolve_missing_order",subjects={"ticket_id":"JIRA-8472","order_id":"ORD-8472","customer_id":"CUS-104"},requested_resolution_semantics="refund_or_replacement",allowed_resolution_paths=("successful_refund","confirmed_replacement"),exclusive_slot="primary_compensation",goodwill_limit_minor_units=5_000,goodwill_currency="USD",completion_evidence=policy.completion_evidence,human_approval_threshold_minor_units=25_000,duplicate_compensation_blocked=True,policy_id=policy.policy_id,policy_version=policy.version)
    return activate_validated_draft(draft,context,policy,namespace=namespace)


def harness(namespace="agents"):
    clock,ledger=VirtualClock(),EconomicLedger(); pact=active_pact(namespace); gateway=IsoPactGatewayInterceptor(pact,InMemoryReservationRepository())
    jira=JiraService(); jira.create_ticket(pact.ticket_id,pact.order_id,pact.customer_id)
    runtime=AgentToolRuntime(gateway=gateway,stripe=StripeService(clock,ledger),carrier=CarrierService(clock,ledger),warehouse=WarehouseService(),crm=CrmService(clock,ledger),jira=jira)
    contexts={role:AgentSessionContext(pact.pact.pact_id,identity,f"session-{role.value.lower()}",f"trace-{role.value.lower()}") for role,identity in IDENTITIES.items()}
    return runtime,contexts


class AgentFleetTests(unittest.TestCase):
    def test_real_adk_agents_have_distinct_tool_inventories(self):
        runtime,contexts=harness("inventory"); fleet=build_adk_fleet(runtime,contexts)
        inventories={role:tuple(sorted(getattr(tool,"name",getattr(tool,"__name__","")) for tool in agent.tools)) for role,agent in fleet.items()}
        self.assertEqual(len(set(inventories.values())),4)
        self.assertIn("request_refund_through_isopact",inventories[AgentRole.SUPPORT])
        self.assertNotIn("request_replacement_through_isopact",inventories[AgentRole.SUPPORT])
        self.assertNotIn("request_refund_through_isopact",inventories[AgentRole.FULFILLMENT])
        self.assertNotIn("request_goodwill_through_isopact",inventories[AgentRole.FULFILLMENT])
        joined=str(inventories)
        for forbidden in ("stripe.create_refund","carrier.create_label","crm.issue_credit","firestore","edit_policy"): self.assertNotIn(forbidden,joined)

    def test_identity_denials_are_deterministic(self):
        runtime,contexts=harness("denial")
        with self.assertRaises(AgentCapabilityDenied): runtime.request_replacement(contexts[AgentRole.SUPPORT])
        with self.assertRaises(AgentCapabilityDenied): runtime.request_refund(contexts[AgentRole.RETENTION])
        with self.assertRaises(AgentCapabilityDenied): AgentCapabilityPolicy.authorize(IDENTITIES[AgentRole.FULFILLMENT],Capability.REQUEST_REFUND)
        self.assertEqual(runtime.gateway.model_calls,0)

    def test_concurrent_support_fulfillment_has_one_primary_execution(self):
        runtime,contexts=harness("race")
        with ThreadPoolExecutor(max_workers=2) as pool:
            support=pool.submit(runtime.request_refund,contexts[AgentRole.SUPPORT])
            fulfillment=pool.submit(runtime.request_replacement,contexts[AgentRole.FULFILLMENT])
        results=(support.result(),fulfillment.result())
        self.assertEqual(sum(item["external_call_executed"] for item in results),1)
        self.assertEqual(sorted(item["gateway_decision"] for item in results),["ALLOW","BLOCK"])

    def test_two_support_sessions_share_semantic_identity(self):
        runtime,contexts=harness("duplicate")
        second=AgentSessionContext(contexts[AgentRole.SUPPORT].pact_id,IDENTITIES[AgentRole.SUPPORT],"session-support-b","trace-support-b")
        first=runtime.request_refund(contexts[AgentRole.SUPPORT]); retry=runtime.request_refund(second)
        self.assertTrue(first["external_call_executed"])
        self.assertFalse(retry["external_call_executed"])
        self.assertEqual(first["operation_identity"],retry["operation_identity"])
        self.assertEqual(runtime.stripe.create_call_count,1)

    def test_retention_cannot_increase_goodwill_limit(self):
        runtime,contexts=harness("goodwill")
        result=runtime.request_goodwill(contexts[AgentRole.RETENTION],5_001)
        self.assertEqual(result["gateway_decision"],"REQUIRE_APPROVAL")
        self.assertFalse(result["external_call_executed"])
        self.assertEqual(result["policy_limit_minor_units"],5_000)

    def test_agent_claim_is_rank_four_and_cannot_settle(self):
        root={"graph_state":"PENDING","selected_resolution":"successful_refund","completion_evidence":{"successful_refund":["stripe.refund.succeeded"]},"evidence_max_rank":{"successful_refund":1},"resolved_operations":{"agent_claim":{"evidence_id":"claim_agent_complete","evidence_type":"agent.interpretation","resolution_path":"successful_refund","state":"SUCCEEDED","rank":4}}}
        self.assertEqual(evaluate_graph(root).state,PactLifecycle.PENDING)
        root["resolved_operations"]["refund"]={"evidence_id":"ev_refund_success","evidence_type":"stripe.refund.succeeded","resolution_path":"successful_refund","state":"SUCCEEDED","rank":1}
        self.assertEqual(evaluate_graph(root).state,PactLifecycle.SETTLED)

    def test_agent_failure_does_not_change_gateway_authority(self):
        runtime,contexts=harness("failure")
        # No model/provider call occurs, but deterministic authority remains available.
        result=runtime.request_refund(contexts[AgentRole.SUPPORT])
        self.assertEqual(result["gateway_decision"],"ALLOW")
        self.assertEqual(runtime.gateway.model_calls,0)


if __name__ == "__main__": unittest.main()
