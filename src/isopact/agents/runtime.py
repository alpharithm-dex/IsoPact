from __future__ import annotations

from threading import Lock

from isopact.gateway.interceptor import IsoPactGatewayInterceptor
from isopact.simulator.models import ScheduledAction
from isopact.simulator.services import CarrierService, CrmService, JiraService, StripeService, WarehouseService

from .authority import AgentCapabilityPolicy
from .models import AgentSessionContext, AgentToolTrace, Capability


class AgentToolRuntime:
    """Typed agent facade; agents receive no service or repository objects."""

    def __init__(self, *, gateway: IsoPactGatewayInterceptor, stripe: StripeService, carrier: CarrierService, warehouse: WarehouseService, crm: CrmService, jira: JiraService, pact_state: str = "OPEN") -> None:
        self.gateway, self.stripe, self.carrier, self.warehouse, self.crm, self.jira = gateway, stripe, carrier, warehouse, crm, jira
        self.pact_state = pact_state
        self.traces: list[AgentToolTrace] = []
        self._counter = 0
        self._lock = Lock()

    def _action_id(self, context: AgentSessionContext, tool: str) -> str:
        with self._lock:
            self._counter += 1
            return f"agent-{context.agent_identity.agent_id}-{tool}-{self._counter:04d}"

    def _trace(self, context, tool, decision=None, operation=None):
        self.traces.append(AgentToolTrace(context.pact_id, context.agent_identity.agent_id, context.agent_identity.google_agent_resource, context.agent_identity.role.value, context.session_id, None, tool, decision, operation, (), (), (), self.pact_state, context.trace_id))

    def inspect_pact(self, context: AgentSessionContext) -> dict:
        AgentCapabilityPolicy.authorize(context.agent_identity, Capability.READ_PACT); self._trace(context, "inspect_pact_state")
        return {"pact_id": context.pact_id, "state": self.pact_state, "authoritative_source": "PACT_GRAPH"}

    def request_refund(self, context: AgentSessionContext, amount_minor_units: int = 20_000) -> dict:
        AgentCapabilityPolicy.authorize(context.agent_identity, Capability.REQUEST_REFUND)
        action = ScheduledAction(self._action_id(context,"refund"), 1, context.agent_identity.agent_id, "stripe", "create_refund", {"amount_minor_units": amount_minor_units, "currency":"USD", "idempotency_key":f"agent-{context.pact_id}-refund", "session_id":context.session_id, "settle_at":None})
        decision=self.gateway.intercept(action); external=False; object_id=None; state="NOT_EXECUTED"
        if decision.decision == "ALLOW":
            refund,_=self.stripe.create_refund(order_id=self.gateway.active_pact.order_id,amount_minor_units=amount_minor_units,currency="USD",idempotency_key=f"agent-{context.pact_id}-refund",actor=context.agent_identity.agent_id,session_id=context.session_id,settle_at=None)
            external=True; object_id=refund["refund_id"]; state=refund["state"]; self.gateway.after_external_call(action,{"status":"OK","object":refund}); self.pact_state="PENDING"
        self._trace(context,"request_refund_through_isopact",decision.decision,decision.operation_identity)
        return {"gateway_decision":decision.decision,"reason_code":decision.reason_code,"external_call_executed":external,"external_object_id":object_id,"external_state":state,"pact_id":context.pact_id,"agent_id":context.agent_identity.agent_id,"session_id":context.session_id,"trace_id":context.trace_id,"operation_identity":decision.operation_identity}

    def request_replacement(self, context: AgentSessionContext) -> dict:
        AgentCapabilityPolicy.authorize(context.agent_identity, Capability.REQUEST_REPLACEMENT)
        action=ScheduledAction(self._action_id(context,"replacement"),1,context.agent_identity.agent_id,"carrier","create_label",{"value_minor_units":20_000,"currency":"USD","session_id":context.session_id})
        decision=self.gateway.intercept(action); external=False; object_id=None; state="NOT_EXECUTED"
        if decision.decision == "ALLOW":
            shipment=self.carrier.create_label(order_id=self.gateway.active_pact.order_id,value_minor_units=20_000,currency="USD",actor=context.agent_identity.agent_id)
            external=True; object_id=shipment["shipment_id"]; state=shipment["state"]; self.gateway.after_external_call(action,{"status":"OK","object":shipment}); self.pact_state="PENDING"
        self._trace(context,"request_replacement_through_isopact",decision.decision,decision.operation_identity)
        return {"gateway_decision":decision.decision,"reason_code":decision.reason_code,"external_call_executed":external,"external_object_id":object_id,"external_state":state,"pact_id":context.pact_id,"agent_id":context.agent_identity.agent_id,"session_id":context.session_id,"trace_id":context.trace_id,"operation_identity":decision.operation_identity}

    def request_goodwill(self, context: AgentSessionContext, amount_minor_units: int = 5_000) -> dict:
        AgentCapabilityPolicy.authorize(context.agent_identity, Capability.REQUEST_GOODWILL)
        action=ScheduledAction(self._action_id(context,"goodwill"),1,context.agent_identity.agent_id,"crm","issue_credit",{"amount_minor_units":amount_minor_units,"currency":"USD","authorized":True,"session_id":context.session_id})
        decision=self.gateway.intercept(action); external=False; object_id=None
        if decision.decision == "ALLOW":
            credit=self.crm.issue_credit(self.gateway.active_pact.customer_id,self.gateway.active_pact.order_id,amount_minor_units,"USD",context.agent_identity.agent_id)
            external=True; object_id=credit["credit_id"]; self.gateway.after_external_call(action,{"status":"OK","object":credit})
        self._trace(context,"request_goodwill_through_isopact",decision.decision,decision.operation_identity)
        return {"gateway_decision":decision.decision,"reason_code":decision.reason_code,"external_call_executed":external,"external_object_id":object_id,"policy_limit_minor_units":self.gateway.active_pact.goodwill_limit_minor_units,"pact_id":context.pact_id,"agent_id":context.agent_identity.agent_id,"session_id":context.session_id,"trace_id":context.trace_id,"operation_identity":decision.operation_identity}
