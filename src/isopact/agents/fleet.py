from __future__ import annotations

import os
from time import perf_counter
from typing import Callable

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.tools.tool_context import ToolContext

from .models import AgentIdentity, AgentRole, AgentSessionContext
from .runtime import AgentToolRuntime


MODEL = "gemini-3.5-flash"

IDENTITIES = {
    AgentRole.SUPPORT: AgentIdentity("isopact-support-v1", AgentRole.SUPPORT, "IsoPact Support Agent", "resolve_missing_order_financially"),
    AgentRole.FULFILLMENT: AgentIdentity("isopact-fulfillment-v1", AgentRole.FULFILLMENT, "IsoPact Fulfillment Agent", "manage_replacement_fulfillment"),
    AgentRole.RETENTION: AgentIdentity("isopact-retention-v1", AgentRole.RETENTION, "IsoPact Retention Agent", "apply_customer_retention_remedy"),
    AgentRole.RESOLVER: AgentIdentity("isopact-resolver-v1", AgentRole.RESOLVER, "IsoPact Settlement Resolver Agent", "reconcile_outcome_conflict"),
}


def _named(name: str, doc: str, fn: Callable):
    fn.__name__ = name; fn.__doc__ = doc; return fn


def build_adk_fleet(runtime: AgentToolRuntime, contexts: dict[AgentRole, AgentSessionContext], *, model: str = MODEL) -> dict[AgentRole, Agent]:
    support_context = contexts[AgentRole.SUPPORT]
    def support_read_pact() -> dict: return runtime.inspect_pact(support_context)
    def support_request_refund(amount_minor_units: int = 20000) -> dict: return runtime.request_refund(support_context, amount_minor_units)
    def read_ticket() -> dict: return {"ticket_id":runtime.gateway.active_pact.ticket_id,"status":"OPEN","pact_id":support_context.pact_id}
    support = Agent(name="support_agent", model=model, description="Financial support specialist for missing-order cases.", instruction="Resolve the customer's financial support objective. Use only your tools. Refunds must use request_refund_through_isopact. Never claim settlement from a PENDING response. Do not perform fulfillment or goodwill work.", tools=[_named("inspect_pact_state","Read authoritative Pact Graph status.",support_read_pact),_named("read_ticket","Read this session's ticket.",read_ticket),_named("request_refund_through_isopact","Request a refund through the deterministic IsoPact Gateway.",support_request_refund)])

    fulfillment_context = contexts[AgentRole.FULFILLMENT]
    def fulfillment_read_pact() -> dict: return runtime.inspect_pact(fulfillment_context)
    def request_replacement() -> dict: return runtime.request_replacement(fulfillment_context)
    def inspect_fulfillment() -> dict: return {"order_id":runtime.gateway.active_pact.order_id,"delivery_status":"MISSING","pact_id":fulfillment_context.pact_id}
    fulfillment = Agent(name="fulfillment_agent", model=model, description="Replacement and fulfillment specialist.", instruction="Pursue a legitimate replacement when fulfillment context warrants it. Use only your tools. Replacement requests must traverse IsoPact. You have no refund or goodwill capability.", tools=[_named("inspect_pact_state","Read authoritative Pact Graph status.",fulfillment_read_pact),_named("inspect_fulfillment_state","Inspect missing-order fulfillment context.",inspect_fulfillment),_named("request_replacement_through_isopact","Request replacement authority through the deterministic IsoPact Gateway.",request_replacement)])

    retention_context = contexts[AgentRole.RETENTION]
    def retention_read_pact() -> dict: return runtime.inspect_pact(retention_context)
    def inspect_customer() -> dict: return {"customer_id":runtime.gateway.active_pact.customer_id,"retention_remedy":"goodwill_up_to_trusted_limit","pact_id":retention_context.pact_id}
    def request_goodwill(amount_minor_units: int = 5000) -> dict: return runtime.request_goodwill(retention_context,amount_minor_units)
    retention = Agent(name="retention_agent", model=model, description="Policy-bounded customer retention specialist.", instruction="Apply only policy-authorized goodwill when appropriate. The tool enforces the trusted limit; you cannot modify it. You have no refund, shipment, warehouse, or policy-edit capability.", tools=[_named("inspect_pact_state","Read authoritative Pact Graph status.",retention_read_pact),_named("inspect_customer_context","Read non-authoritative retention context.",inspect_customer),_named("request_goodwill_through_isopact","Request goodwill through the deterministic IsoPact Gateway.",request_goodwill)])

    resolver_context = contexts[AgentRole.RESOLVER]
    def resolver_read_pact() -> dict: return runtime.inspect_pact(resolver_context)
    def get_open_conflicts() -> dict: return {"conflicts":["COMMERCE_PRIMARY_RESOLUTION_EXCLUSIVE"],"state":"VIOLATED","pact_id":resolver_context.pact_id}
    def get_available_compensation_candidates() -> dict: return {"candidate_ids":["carrier_cancel_unaccepted_label_v1","warehouse_release_reserved_stock_v1"],"raw_tools_exposed":False}
    def request_validated_resolution_plan(selected_registry_action_ids: list[str]) -> dict:
        allowed={"carrier_cancel_unaccepted_label_v1","warehouse_release_reserved_stock_v1"}
        valid=set(selected_registry_action_ids)<=allowed and bool(selected_registry_action_ids)
        return {"validation":"VALID_AUTOMATIC" if valid else "REJECTED","selected_registry_action_ids":selected_registry_action_ids if valid else [],"stage7_validator_authoritative":True,"execution_not_performed":True}
    resolver = Agent(name="settlement_resolver_agent",model=model,description="Conflict reasoning agent constrained by the Stage 7 registry.",instruction="Coordinate recovery from deterministic conflicts. Select only candidate IDs returned by the registry tool. request_validated_resolution_plan invokes deterministic validation; it is not execution. You cannot self-approve or call compensation systems.",tools=[_named("inspect_pact_state","Read authoritative Pact Graph status.",resolver_read_pact),_named("get_open_conflicts","Read deterministic conflicts.",get_open_conflicts),_named("get_available_compensation_candidates","Read trusted Stage 7 registry candidates.",get_available_compensation_candidates),_named("request_validated_resolution_plan","Submit only registry IDs to deterministic Stage 7 validation.",request_validated_resolution_plan)])
    return {AgentRole.SUPPORT:support,AgentRole.FULFILLMENT:fulfillment,AgentRole.RETENTION:retention,AgentRole.RESOLVER:resolver}


def _gateway_url() -> str:
    value = os.environ.get("ISOPACT_OUTCOME_GATEWAY_URL", "").rstrip("/")
    if not value:
        raise RuntimeError("ISOPACT_OUTCOME_GATEWAY_URL is not configured")
    return value


def _mint_gateway_token(role: AgentRole) -> str:
    """Obtain a Google-signed audience-bound token from the runtime metadata service."""
    from google.auth.transport.requests import Request
    from google.oauth2.id_token import fetch_id_token

    del role  # The deployed resource identity, not caller input, determines the subject.
    return fetch_id_token(Request(), _gateway_url())


def _call_outcome_gateway(
    role: AgentRole,
    method: str,
    path: str,
    payload: dict | None = None,
    *,
    invocation_id: str | None = None,
) -> dict:
    """Call private Cloud Run while preserving the signed logical caller identity."""
    import base64
    import json
    import requests

    started = perf_counter()
    from isopact.observability import telemetry
    with telemetry.span(
        "isopact.agent.invoke",
        **{
            "isopact.agent.role": role.value,
            "isopact.tool.path": path,
            "gcp.vertex.agent.invocation_id": invocation_id,
        },
    ):
        token = _mint_gateway_token(role)
        try:
            encoded = token.split(".")[1]
            encoded += "=" * (-len(encoded) % 4)
            raw_claims = json.loads(base64.urlsafe_b64decode(encoded).decode())
            safe_token_claims = {
                key: raw_claims.get(key) for key in ("iss", "sub", "email", "aud")
                if raw_claims.get(key) is not None
            }
        except Exception:
            safe_token_claims = {"decode": "unavailable"}
        headers = {"Authorization": f"Bearer {token}"}
        otel_trace_id, otel_span_id = telemetry.context_ids()
        telemetry.inject(headers)
        trace_context_injected = "traceparent" in {
            key.lower(): value for key, value in headers.items()
        }
        response = requests.request(
            method,
            f"{_gateway_url()}{path}",
            json=payload,
            headers=headers,
            timeout=30,
        )
    elapsed_ms = (perf_counter() - started) * 1000
    try:
        result = response.json()
    except ValueError:
        result = {"error": "NON_JSON_GATEWAY_RESPONSE", "body": response.text[:500]}
    result.update({
        "http_status": response.status_code,
        "agent_runtime_region": "europe-west1",
        "cross_region_round_trip_ms": round(elapsed_ms, 3),
        "safe_token_claims": safe_token_claims,
        "w3c_trace_context_injected": trace_context_injected,
        "otel_trace_id": otel_trace_id,
        "otel_span_id": otel_span_id,
    })
    return result


def _inspect_as(role: AgentRole, pact_id: str, tool_context: ToolContext) -> dict:
    return _call_outcome_gateway(
        role,
        "GET",
        f"/v1/pacts/{pact_id}/status",
        invocation_id=tool_context.invocation_id,
    )


def support_inspect_pact_state(pact_id: str, tool_context: ToolContext) -> dict:
    """Read minimal authoritative pact status as the Support identity."""
    return _inspect_as(AgentRole.SUPPORT, pact_id, tool_context)


def fulfillment_inspect_pact_state(pact_id: str, tool_context: ToolContext) -> dict:
    """Read minimal authoritative pact status as the Fulfillment identity."""
    return _inspect_as(AgentRole.FULFILLMENT, pact_id, tool_context)


def retention_inspect_pact_state(pact_id: str, tool_context: ToolContext) -> dict:
    """Read minimal authoritative pact status as the Retention identity."""
    return _inspect_as(AgentRole.RETENTION, pact_id, tool_context)


def resolver_inspect_pact_state(pact_id: str, tool_context: ToolContext) -> dict:
    """Read minimal authoritative pact status as the Resolver identity."""
    return _inspect_as(AgentRole.RESOLVER, pact_id, tool_context)


def request_refund_through_isopact(
    pact_id: str, order_id: str, session_id: str, trace_id: str, request_id: str,
    amount_minor_units: int = 20000, body_agent_id: str = "",
    tool_context: ToolContext = None,
) -> dict:
    """Execute a Support refund request through the authenticated IsoPact Gateway."""
    return _call_outcome_gateway(AgentRole.SUPPORT, "POST", f"/v1/pacts/{pact_id}/actions/refund", {
        "order_id": order_id, "session_id": session_id, "trace_id": trace_id,
        "request_id": request_id, "amount_minor_units": amount_minor_units,
        "agent_id": body_agent_id,
    }, invocation_id=tool_context.invocation_id if tool_context else None)


def request_replacement_through_isopact(
    pact_id: str, order_id: str, session_id: str, trace_id: str, request_id: str,
    tool_context: ToolContext = None,
) -> dict:
    """Execute a Fulfillment replacement request through the authenticated IsoPact Gateway."""
    return _call_outcome_gateway(AgentRole.FULFILLMENT, "POST", f"/v1/pacts/{pact_id}/actions/replacement", {
        "order_id": order_id, "session_id": session_id, "trace_id": trace_id,
        "request_id": request_id,
    }, invocation_id=tool_context.invocation_id if tool_context else None)


def request_goodwill_through_isopact(
    pact_id: str, customer_id: str, session_id: str, trace_id: str, request_id: str,
    amount_minor_units: int = 5000,
    tool_context: ToolContext = None,
) -> dict:
    """Execute a Retention goodwill request through the authenticated IsoPact Gateway."""
    return _call_outcome_gateway(AgentRole.RETENTION, "POST", f"/v1/pacts/{pact_id}/actions/goodwill", {
        "customer_id": customer_id, "session_id": session_id, "trace_id": trace_id,
        "request_id": request_id, "amount_minor_units": amount_minor_units,
    }, invocation_id=tool_context.invocation_id if tool_context else None)

def get_available_compensation_candidates(pact_id: str) -> dict:
    """Return only trusted Stage 7 registry IDs; no raw compensation tools."""
    return {"pact_id":pact_id,"candidate_ids":["carrier_cancel_unaccepted_label_v1","warehouse_release_reserved_stock_v1"],"closed_action_space":True}

def request_validated_resolution_plan(
    pact_id: str, selected_registry_action_ids: list[str], session_id: str,
    trace_id: str, request_id: str,
    tool_context: ToolContext = None,
) -> dict:
    """Submit closed-registry IDs to deterministic Stage 7 validation; never execute them."""
    return _call_outcome_gateway(AgentRole.RESOLVER, "POST", f"/v1/pacts/{pact_id}/resolution-plans", {
        "selected_registry_action_ids": selected_registry_action_ids,
        "session_id": session_id, "trace_id": trace_id, "request_id": request_id,
    }, invocation_id=tool_context.invocation_id if tool_context else None)

def build_deployment_agent(role: AgentRole, *, model: str = MODEL) -> App:
    identity=IDENTITIES[role]
    if role is AgentRole.SUPPORT:
        instruction="Support missing-order customers financially. Use only request_refund_through_isopact and pact reads. Always pass the supplied session_id, trace_id, and request_id exactly. Do not claim PENDING work is settled."
        tools=[support_inspect_pact_state,request_refund_through_isopact]
    elif role is AgentRole.FULFILLMENT:
        instruction="Handle replacement fulfillment. Use only request_replacement_through_isopact and pact reads. Always pass the supplied session_id, trace_id, and request_id exactly. You cannot refund or issue goodwill."
        tools=[fulfillment_inspect_pact_state,request_replacement_through_isopact]
    elif role is AgentRole.RETENTION:
        instruction="Apply policy-bounded retention remedies. Use only request_goodwill_through_isopact and pact reads. Always pass the supplied session_id, trace_id, and request_id exactly. You cannot edit policy."
        tools=[retention_inspect_pact_state,request_goodwill_through_isopact]
    else:
        instruction="Reason over deterministic conflicts and request only Stage 7 registry candidates. Always pass the supplied session_id, trace_id, and request_id exactly. You cannot execute or approve compensation."
        tools=[resolver_inspect_pact_state,get_available_compensation_candidates,request_validated_resolution_plan]
    agent=Agent(name=f"{role.value.lower()}_agent",model=model,description=f"{identity.display_name}; skill={identity.skill_id}",instruction=instruction,tools=tools)
    return App(name=f"isopact_{role.value.lower()}_app",root_agent=agent)


def _support_a2a_executor():
    """Build the official ADK-to-A2A executor lazily inside Agent Runtime."""
    from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
    from google.adk.models.google_llm import Gemini
    from google.adk.runners import Runner
    from google.adk.sessions.in_memory_session_service import InMemorySessionService

    model = Gemini(
        model=MODEL,
        client_kwargs={
            "vertexai": True,
            "project": "isopact-agentic-20260823",
            "location": "global",
        },
    )
    app = build_deployment_agent(AgentRole.SUPPORT, model=model)
    runner = Runner(
        app_name=app.name,
        agent=app.root_agent,
        session_service=InMemorySessionService(),
    )
    return A2aAgentExecutor(runner=runner)


def build_support_a2a_agent():
    """Build a genuine Google A2A template with an accurate Support skill card."""
    from a2a.types import AgentSkill
    from agentplatform.agent_engines.templates.a2a import A2aAgent, create_agent_card

    skill = AgentSkill(
        id=IDENTITIES[AgentRole.SUPPORT].skill_id,
        name="Resolve missing order financially",
        description="Inspect pact state and submit a refund request only through the IsoPact Gateway.",
        tags=["support", "missing-order", "isopact"],
        examples=["Resolve the financial remedy for missing order ORD-8472 under pact PACT-123."],
    )
    card = create_agent_card(
        agent_name="IsoPact Support Agent A2A v1",
        description="A capability-bounded Support agent; no raw payment or fulfillment tools.",
        skills=[skill],
        streaming=True,
    )
    agent = A2aAgent(agent_card=card, agent_executor_builder=_support_a2a_executor)
    agent.set_up()
    return agent
