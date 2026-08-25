from __future__ import annotations

import os
import re
import copy
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from flask import Flask, jsonify, request
from google.cloud import firestore
import jwt

from isopact.agents.authority import AgentCapabilityDenied, AgentCapabilityPolicy
from isopact.agents.models import AgentIdentity, AgentRole, Capability
from isopact.domain.models import Money, OutcomePact, PolicyVersion, ResolutionSlot
from isopact.evidence.firestore import FirestorePactGraphRepository
from isopact.evidence.models import ClaimType, EvidenceRank, ImmediateState, StateClaim
from isopact.evidence.pipeline import EvidencePipeline
from isopact.gateway.activation import ActiveOutcomePact
from isopact.gateway.interceptor import IsoPactGatewayInterceptor
from isopact.reservations.firestore import FirestoreReservationRepository
from isopact.resolver.registry import default_compensation_registry
from isopact.simulator.models import ScheduledAction
from isopact.security.agent_tokens import verify_agent_identity_token
from isopact.observability import telemetry
from isopact.observability.chronicle import build_case_chronicle
from isopact.security.provenance import verify_integrity_bundle


PROJECT = os.environ.get("ISOPACT_PROJECT", "isopact-agentic-20260823")
DATABASE = os.environ.get("ISOPACT_DATABASE", "(default)")
EXPECTED_AUDIENCE = os.environ.get("ISOPACT_EXPECTED_AUDIENCE", "")
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,180}$")
PROJECT_NUMBER = os.environ.get("ISOPACT_PROJECT_NUMBER", "442539309409")
AGENT_ENGINES = {
    AgentRole.SUPPORT: "1997126532413259776",
    AgentRole.FULFILLMENT: "7471674091947163648",
    AgentRole.RETENTION: "1103584218845282304",
    AgentRole.RESOLVER: "4435825730634383360",
}
IDENTITIES = {
    AgentRole.SUPPORT: AgentIdentity("isopact-support-v1", AgentRole.SUPPORT, "IsoPact Support Agent", "resolve_missing_order_financially"),
    AgentRole.FULFILLMENT: AgentIdentity("isopact-fulfillment-v1", AgentRole.FULFILLMENT, "IsoPact Fulfillment Agent", "manage_replacement_fulfillment"),
    AgentRole.RETENTION: AgentIdentity("isopact-retention-v1", AgentRole.RETENTION, "IsoPact Retention Agent", "apply_customer_retention_remedy"),
    AgentRole.RESOLVER: AgentIdentity("isopact-resolver-v1", AgentRole.RESOLVER, "IsoPact Settlement Resolver Agent", "reconcile_outcome_conflict"),
}
AGENT_ISSUER = (
    f"https://sts.googleapis.com/v1/projects/{PROJECT_NUMBER}/locations/global/"
    f"workloadIdentityPools/agents.global.proj-{PROJECT_NUMBER}.system.id.goog"
)
AGENT_SUBJECTS = {
    (
        f"spiffe://agents.global.proj-{PROJECT_NUMBER}.system.id.goog/resources/"
        f"aiplatform/projects/{PROJECT_NUMBER}/locations/europe-west1/reasoningEngines/{engine}"
    ): role
    for role, engine in AGENT_ENGINES.items()
}
jwks = jwt.PyJWKClient(f"{AGENT_ISSUER}/openid/jwks", cache_keys=True)

STAGE11_FRONTEND = Path(os.environ.get("ISOPACT_STAGE11_FRONTEND", "/app/frontend"))
STAGE11_PACT_ID = os.environ.get(
    "ISOPACT_STAGE11_PACT_ID",
    "pact_stage8b-e2e-20260824205251_eb00881cf40576cb2793",
)
STAGE11_DATA_PATH = STAGE11_FRONTEND / "data" / "stage11-data.json"
STAGE11_PUBLIC_KEYS = Path(os.environ.get("ISOPACT_STAGE11_PUBLIC_KEYS", "/app/stage11-security/public-keys.json"))

app = Flask(__name__, static_folder=str(STAGE11_FRONTEND), static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 1_048_576


@app.after_request
def harden_public_http(response):
    """Apply same-origin browser hardening without changing agent authentication."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if request.path.startswith("/v1/"):
        response.headers["Cache-Control"] = "no-store"
    return response
db = firestore.Client(project=PROJECT, database=DATABASE)
reservations = FirestoreReservationRepository(PROJECT, DATABASE, client=db)
graph = FirestorePactGraphRepository(PROJECT, DATABASE, client=db)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _error(status: int, code: str, message: str, **extra):
    return jsonify({"error": code, "message": message, **extra}), status


def _safe_id(value: Any, field: str) -> str:
    text = str(value or "")
    if not SAFE_ID.fullmatch(text):
        raise ValueError(f"invalid {field}")
    return text


def authenticated_identity() -> tuple[Any, AgentRole, dict[str, Any]]:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer ") or not EXPECTED_AUDIENCE:
        raise PermissionError("missing signed caller token")
    token = header.removeprefix("Bearer ").strip()
    role, auth = verify_agent_identity_token(
        token, jwks_client=jwks, expected_issuer=AGENT_ISSUER,
        expected_audience=EXPECTED_AUDIENCE, subject_roles=AGENT_SUBJECTS,
    )
    identity = IDENTITIES[role]
    return identity, role, auth


def active_pact_from_document(pact_id: str) -> tuple[ActiveOutcomePact, dict[str, Any]]:
    snapshot = db.collection("pacts").document(pact_id).get()
    if not snapshot.exists:
        raise KeyError(f"unknown pact {pact_id}")
    data = snapshot.to_dict()
    paths = frozenset(data["allowed_resolution_paths"])
    slots = {
        name: frozenset(values)
        for name, values in data["exclusive_slots"].items()
    }
    transaction = data["transaction"]
    active = ActiveOutcomePact(
        pact=OutcomePact(
            pact_id=pact_id,
            transaction=Money(str(transaction["currency"]), int(transaction["minor_units"])),
            allowed_resolution_paths=paths,
            exclusive_slots=slots,
            policy=PolicyVersion(str(data["policy_id"]), str(data["policy_version"])),
        ),
        order_id=str(data["order_id"]),
        customer_id=str(data["customer_id"]),
        ticket_id=str(data["ticket_id"]),
        goodwill_limit_minor_units=int(data["goodwill_limit_minor_units"]),
        goodwill_currency=str(data["goodwill_currency"]),
        completion_evidence={key: tuple(value) for key, value in data["completion_evidence"].items()},
        evidence_max_rank={key: int(value) for key, value in data["evidence_max_rank"].items()},
        evaluation_rule_set_id=str(data.get("evaluation_rule_set_id", "commerce_missing_order_rules")),
        evaluation_rule_set_version=str(data.get("evaluation_rule_set_version", "1")),
    )
    return active, data


def external_execute(
    *, pact_id: str, operation_identity: str, action_kind: str, actor: str, request_id: str
) -> dict[str, Any]:
    object_id = {
        "refund": f"REF-{operation_identity[:12]}",
        "replacement": f"SHIP-{operation_identity[:12]}",
        "goodwill": f"CR-{operation_identity[:12]}",
    }[action_kind]
    state = {"refund": "PENDING", "replacement": "CREATED", "goodwill": "ISSUED"}[action_kind]
    payload = {
        "external_object_id": object_id,
        "kind": action_kind,
        "state": state,
        "operation_identity": operation_identity,
        "actor": actor,
        "request_id": request_id,
        "created_at": utc_now(),
        "adapter": "FIRESTORE_BACKED_ENTERPRISE_SIMULATOR",
    }
    db.collection("pacts").document(pact_id).collection("external_objects").document(operation_identity).create(payload)
    return payload


def record_pending_claim(
    *, pact_id: str, identity, role: AgentRole, operation_identity: str,
    action_kind: str, external: dict[str, Any], trace_id: str, request_id: str,
) -> None:
    path = {
        "refund": "successful_refund",
        "replacement": "confirmed_replacement",
        "goodwill": "authorized_goodwill",
    }[action_kind]
    now = utc_now()
    EvidencePipeline(graph).record_claim(
        StateClaim(
            claim_id=f"claim_remote_{request_id}",
            pact_id=pact_id,
            claim_type=ClaimType.API_RESPONSE,
            source_system={"refund": "stripe", "replacement": "carrier", "goodwill": "crm"}[action_kind],
            source_actor=identity.agent_id,
            subject=action_kind,
            external_object_id=external["external_object_id"],
            operation_identity=operation_identity,
            resolution_path=path,
            immediate_state=ImmediateState.PENDING if action_kind == "refund" else ImmediateState.ACCEPTED,
            evidence_rank=EvidenceRank.ACCEPTED_PENDING_RESPONSE,
            occurred_at=now,
            ingested_at=now,
            trace_id=trace_id,
            references=(f"remote-role:{role.value}",),
            agent_identity=identity.agent_id,
            policy_references=("commerce_missing_order_v1@1",),
            rule_references=("commerce_missing_order_rules@1",),
            normalized_payload={
                "action_kind": action_kind,
                "external_object_id": external["external_object_id"],
                "external_state": external["state"],
                "immediate_state": "PENDING" if action_kind == "refund" else "ACCEPTED",
            },
            protected_references=(f"external:{external['external_object_id']}",),
        )
    )


def record_gateway_decision_claim(
    *, pact_id: str, identity, role: AgentRole, action_kind: str, decision,
    trace_id: str, request_id: str, normalized_inputs: dict[str, Any],
) -> None:
    now = utc_now()
    graph.append_claim(StateClaim(
        claim_id=f"claim_gateway_{request_id}", pact_id=pact_id,
        claim_type=ClaimType.GATEWAY_AUTHORIZATION, source_system="isopact-outcome-gateway",
        source_actor=identity.agent_id, subject=action_kind, external_object_id=None,
        operation_identity=decision.operation_identity, resolution_path={
            "refund": "successful_refund", "replacement": "confirmed_replacement",
            "goodwill": "authorized_goodwill",
        }[action_kind],
        immediate_state=ImmediateState.ACCEPTED if decision.decision == "ALLOW" else ImmediateState.UNKNOWN,
        evidence_rank=EvidenceRank.AGENT_INTERPRETATION, occurred_at=now, ingested_at=now,
        trace_id=trace_id, references=(f"gateway-decision:{decision.reason_code}",),
        agent_identity=identity.agent_id,
        policy_references=("commerce_missing_order_v1@1",),
        rule_references=("commerce_missing_order_rules@1",),
        normalized_payload={
            "action_kind": action_kind, "authorization_result": decision.decision,
            "reason_code": decision.reason_code, "request_id": request_id,
            "role": role.value, "inputs": normalized_inputs,
        },
    ))


def _action_response(pact_id: str, action_kind: str):
    full_started = perf_counter()
    try:
        auth_started = perf_counter()
        with telemetry.span("isopact.gateway.authenticate"):
            identity, role, auth = authenticated_identity()
        auth_ms = (perf_counter() - auth_started) * 1000
        capability = {
            "refund": Capability.REQUEST_REFUND,
            "replacement": Capability.REQUEST_REPLACEMENT,
            "goodwill": Capability.REQUEST_GOODWILL,
        }[action_kind]
        AgentCapabilityPolicy.authorize(identity, capability)
        pact_id = _safe_id(pact_id, "pact_id")
        body = request.get_json(silent=True) or {}
        session_id = _safe_id(body.get("session_id"), "session_id")
        trace_id = _safe_id(body.get("trace_id"), "trace_id")
        request_id = _safe_id(body.get("request_id"), "request_id")
        active, pact_doc = active_pact_from_document(pact_id)

        if action_kind == "refund":
            inputs = {
                "amount_minor_units": int(body.get("amount_minor_units", active.pact.transaction.minor_units)),
                "currency": str(body.get("currency", active.pact.transaction.currency)),
                "idempotency_key": f"remote-{pact_id}-refund",
                "session_id": session_id,
            }
            target, tool = "stripe", "create_refund"
        elif action_kind == "replacement":
            inputs = {"value_minor_units": active.pact.transaction.minor_units, "currency": active.pact.transaction.currency, "session_id": session_id}
            target, tool = "carrier", "create_label"
        else:
            inputs = {"amount_minor_units": int(body.get("amount_minor_units", 5_000)), "currency": str(body.get("currency", "USD")), "authorized": True, "session_id": session_id}
            target, tool = "crm", "issue_credit"
        action = ScheduledAction(request_id, 1, identity.agent_id, target, tool, inputs)
        gateway = IsoPactGatewayInterceptor(active, reservations)
        gateway_started = perf_counter()
        with telemetry.span("isopact.gateway.authorize", **{"isopact.pact_id": pact_id, "isopact.agent.role": role.value}):
            reservation_started = perf_counter()
            with telemetry.span("isopact.reservation.transaction"):
                decision = gateway.intercept(action)
            telemetry.observe(
                "isopact.reservation.duration",
                (perf_counter() - reservation_started) * 1000,
                decision_type=decision.decision,
                agent_role=role.value,
            )
            telemetry.add("isopact.gateway.decisions", decision_type=decision.decision, reason_code=decision.reason_code, agent_role=role.value)
            if decision.decision == "BLOCK" and decision.reason_code == "DUPLICATE_OPERATION":
                telemetry.add("isopact.duplicate_operations_blocked", reason_code=decision.reason_code, agent_role=role.value)
            if decision.decision == "BLOCK" and decision.reason_code == "EXCLUSIVE_RESOLUTION_CONFLICT":
                telemetry.add("isopact.exclusive_conflicts_blocked", reason_code=decision.reason_code, agent_role=role.value)
            telemetry.log("INFO" if decision.decision == "ALLOW" else "WARNING", "gateway action decision", **{"isopact.pact_id": pact_id, "isopact.agent.role": role.value, "isopact.decision": decision.decision, "isopact.reason_code": decision.reason_code, "isopact.external.executed": decision.decision == "ALLOW"})
        gateway_ms = (perf_counter() - gateway_started) * 1000
        record_gateway_decision_claim(
            pact_id=pact_id, identity=identity, role=role, action_kind=action_kind,
            decision=decision, trace_id=trace_id, request_id=request_id,
            normalized_inputs={
                key: value for key, value in inputs.items()
                if key not in {"idempotency_key"}
            },
        )
        external = None
        external_ms = 0.0
        if decision.decision == "ALLOW":
            external_started = perf_counter()
            with telemetry.span(f"isopact.external.{action_kind}", **{"isopact.external.executed": True, "isopact.pact_id": pact_id}):
                external = external_execute(
                    pact_id=pact_id, operation_identity=decision.operation_identity,
                    action_kind=action_kind, actor=identity.agent_id, request_id=request_id,
                )
            gateway.after_external_call(action, {"status": "OK", "object": external})
            record_pending_claim(
                pact_id=pact_id,
                identity=identity,
                role=role,
                operation_identity=decision.operation_identity,
                action_kind=action_kind,
                external=external,
                trace_id=trace_id,
                request_id=request_id,
            )
            external_ms = (perf_counter() - external_started) * 1000
        root = db.collection("pacts").document(pact_id).get().to_dict() or {}
        supplied_identity = body.get("agent_id")
        response = {
            "pact_id": pact_id,
            "verified_agent_id": identity.agent_id,
            "verified_role": role.value,
            "verified_caller": auth,
            "body_agent_id_supplied": supplied_identity,
            "body_identity_used_for_authority": False,
            "session_id": session_id,
            "trace_id": trace_id,
            "request_id": request_id,
            "action": action_kind,
            "gateway_decision": decision.decision,
            "reason_code": decision.reason_code,
            "operation_identity": decision.operation_identity,
            "external_call_executed": external is not None,
            "external_object": external,
            "pact_graph_state": root.get("graph_state", "OPEN"),
            "timing_ms": {
                "identity_verification": round(auth_ms, 3),
                "gateway_authorization_including_firestore": round(gateway_ms, 3),
                "external_adapter_and_claim": round(external_ms, 3),
                "full_server": round((perf_counter() - full_started) * 1000, 3),
            },
            "regions": {"outcome_gateway": "africa-south1", "firestore": "africa-south1"},
        }
        status = 200 if decision.decision == "ALLOW" else 409
        telemetry.observe("isopact.gateway.authorization.duration", gateway_ms, decision_type=decision.decision, agent_role=role.value)
        if external is not None:
            telemetry.add("isopact.external.executions", tool_category=action_kind, agent_role=role.value)
        return jsonify(response), status
    except AgentCapabilityDenied as exc:
        return _error(403, "CAPABILITY_DENIED", str(exc), external_call_executed=False)
    except PermissionError as exc:
        return _error(401, "CALLER_IDENTITY_INVALID", str(exc), external_call_executed=False)
    except KeyError as exc:
        return _error(404, "PACT_NOT_FOUND", str(exc), external_call_executed=False)
    except (ValueError, TypeError) as exc:
        return _error(400, "INVALID_REQUEST", str(exc), external_call_executed=False)
    except Exception as exc:
        app.logger.exception("outcome gateway failure")
        return _error(503, "SETTLEMENT_PLANE_UNAVAILABLE", type(exc).__name__, external_call_executed=False)


def action_response(pact_id: str, action_kind: str):
    # Preserve a valid Runtime/tool trace when supplied. Invalid or absent
    # context safely produces a new trace through the normal propagator.
    carrier = {key.lower(): value for key, value in request.headers.items()}
    with telemetry.remote_context(carrier):
        with telemetry.span(
            "isopact.gateway.request",
            **{"isopact.pact_id": pact_id, "isopact.action": action_kind},
        ):
            return _action_response(pact_id, action_kind)


@app.post("/v1/pacts/<pact_id>/actions/refund")
def refund(pact_id: str):
    return action_response(pact_id, "refund")


@app.post("/v1/pacts/<pact_id>/actions/replacement")
def replacement(pact_id: str):
    return action_response(pact_id, "replacement")


@app.post("/v1/pacts/<pact_id>/actions/goodwill")
def goodwill(pact_id: str):
    return action_response(pact_id, "goodwill")


@app.post("/v1/pacts/<pact_id>/resolution-plans")
def resolution_plan(pact_id: str):
    try:
        identity, role, auth = authenticated_identity()
        AgentCapabilityPolicy.authorize(identity, Capability.REQUEST_VALIDATED_PLAN)
        pact_id = _safe_id(pact_id, "pact_id")
        body = request.get_json(silent=True) or {}
        selected = [str(value) for value in body.get("selected_registry_action_ids", [])]
        registry = default_compensation_registry()
        for action_id in selected:
            registry.get(action_id)
        return jsonify({
            "pact_id": pact_id,
            "verified_agent_id": identity.agent_id,
            "verified_role": role.value,
            "verified_caller": auth,
            "selected_registry_action_ids": selected,
            "status": "STAGE7_VALIDATION_REQUIRED",
            "execution_performed": False,
            "approval_bypass_available": False,
        })
    except AgentCapabilityDenied as exc:
        return _error(403, "CAPABILITY_DENIED", str(exc), external_call_executed=False)
    except PermissionError as exc:
        return _error(401, "CALLER_IDENTITY_INVALID", str(exc), external_call_executed=False)
    except ValueError as exc:
        return _error(400, "UNREGISTERED_COMPENSATION", str(exc), external_call_executed=False)


@app.get("/v1/pacts/<pact_id>/status")
def status(pact_id: str):
    try:
        identity, role, auth = authenticated_identity()
        AgentCapabilityPolicy.authorize(identity, Capability.READ_PACT)
        pact_id = _safe_id(pact_id, "pact_id")
        _, data = active_pact_from_document(pact_id)
        return jsonify({
            "pact_id": pact_id,
            "status": data.get("graph_state", data.get("status", "OPEN")),
            "verified_agent_id": identity.agent_id,
            "verified_role": role.value,
            "verified_caller": auth,
            "authoritative_source": "PACT_GRAPH_FIRESTORE",
            "returned_fields": ["pact_id", "status"],
        })
    except PermissionError as exc:
        return _error(401, "CALLER_IDENTITY_INVALID", str(exc))
    except KeyError as exc:
        return _error(404, "PACT_NOT_FOUND", str(exc))


def _authorized_chronicle(pact_id: str):
    identity, role, auth = authenticated_identity()
    AgentCapabilityPolicy.authorize(identity, Capability.READ_PACT)
    pact_id = _safe_id(pact_id, "pact_id")
    ref = db.collection("pacts").document(pact_id)
    snapshot = ref.get()
    if not snapshot.exists:
        raise KeyError(f"unknown pact {pact_id}")
    names = ("claims", "conflicts", "invariant_conflicts", "settlement_receipts")
    derived = build_case_chronicle(snapshot.to_dict(), {name: [doc.to_dict() for doc in ref.collection(name).stream()] for name in names})
    derived["verified_reader"] = {"agent_id": identity.agent_id, "role": role.value}
    return derived


def _demo_pact_ref():
    """Return the single sanitized judge-demo pact; never accept an arbitrary ID."""
    pact_id = _safe_id(STAGE11_PACT_ID, "pact_id")
    ref = db.collection("pacts").document(pact_id)
    snapshot = ref.get()
    if not snapshot.exists:
        raise KeyError(f"unknown configured demo pact {pact_id}")
    return pact_id, ref, snapshot


def _stage11_data() -> dict[str, Any]:
    data = json.loads(STAGE11_DATA_PATH.read_text(encoding="utf-8"))
    pact_id, ref, snapshot = _demo_pact_ref()
    receipt_docs = list(ref.collection("settlement_receipts").stream())
    primary = next(item for item in data["scenarios"] if item["id"] == "protected")
    primary["pactId"] = pact_id
    primary["evidenceMode"] = "LIVE"
    data["generatedAt"] = utc_now()
    data["liveBackend"] = {
        "source": "PACT_GRAPH_FIRESTORE",
        "pactId": pact_id,
        "currentLifecycle": (snapshot.to_dict() or {}).get("graph_state", "OPEN"),
        "receiptCount": len(receipt_docs),
        "readAt": utc_now(),
        "silentReplayFallback": False,
    }
    return data


def _live_integrity(proof: str) -> dict[str, Any]:
    pact_id, ref, _ = _demo_pact_ref()
    receipts = [doc.to_dict() for doc in ref.collection("settlement_receipts").stream()]
    checkpoints = [doc.to_dict() for doc in ref.collection("graph_checkpoints").stream()]
    claims = [doc.to_dict() for doc in ref.collection("claims").stream()]
    if not receipts or not checkpoints or not claims:
        raise KeyError("configured demo pact lacks a complete integrity bundle")
    receipt = max(receipts, key=lambda item: int((item.get("final_checkpoint") or {}).get("through_sequence", 0)))
    checkpoint_id = (receipt.get("final_checkpoint") or {}).get("checkpoint_id")
    checkpoint = next((item for item in checkpoints if item.get("checkpoint_id") == checkpoint_id), None)
    if checkpoint is None:
        raise KeyError("receipt checkpoint not found")
    through_sequence = int(checkpoint.get("through_sequence", 0))
    claims = [
        item for item in claims
        if 1 <= int(item.get("sequence_number", item.get("sequence", 0))) <= through_sequence
    ]
    claims.sort(key=lambda item: int(item.get("sequence_number", item.get("sequence", 0))))
    public_keys = json.loads(STAGE11_PUBLIC_KEYS.read_text(encoding="utf-8"))
    candidate = copy.deepcopy(receipt)
    if proof == "TAMPERED_ARTIFACT":
        economic = candidate.setdefault("economic_position", {})
        economic["settled_total_compensation"] = int(economic.get("settled_total_compensation", 0)) + 1
    result = verify_integrity_bundle(
        receipt=candidate, checkpoint=checkpoint, claims=claims, public_keys=public_keys,
    )
    return {
        **result,
        "proof": proof,
        "pact_id": pact_id,
        "receipt_id": receipt.get("receipt_id"),
        "authoritative_source": "PACT_GRAPH_FIRESTORE",
        "production_data_modified": False,
    }


@app.get("/v1/pacts/<pact_id>/chronicle")
def chronicle(pact_id: str):
    try:
        return jsonify(_authorized_chronicle(pact_id))
    except PermissionError as exc:
        return _error(401, "CALLER_IDENTITY_INVALID", str(exc))
    except KeyError as exc:
        return _error(404, "PACT_NOT_FOUND", str(exc))


@app.get("/v1/pacts/<pact_id>/observability")
def observability(pact_id: str):
    try:
        chron = _authorized_chronicle(pact_id)
        return jsonify({"pact_id": chron["pact_id"], "current_lifecycle": chron["current_lifecycle"], "trace_ids": chron["trace_ids"], "conflicts": chron["conflicts"], "receipt_verification": chron["receipt_verification"], "authoritative_source": "PACT_GRAPH_DERIVED_READ_ONLY"})
    except PermissionError as exc:
        return _error(401, "CALLER_IDENTITY_INVALID", str(exc))
    except KeyError as exc:
        return _error(404, "PACT_NOT_FOUND", str(exc))


@app.get("/v1/demo/stage11")
def stage11_demo():
    """Sanitized, read-only judge projection over the configured authoritative case."""
    try:
        return jsonify(_stage11_data())
    except (KeyError, OSError) as exc:
        return _error(503, "LIVE_DEMO_UNAVAILABLE", str(exc))


@app.post("/v1/demo/stage11/receipts/verify")
def stage11_verify_receipt():
    try:
        body = request.get_json(silent=True) or {}
        proof = str(body.get("proof", "LIVE"))
        if proof not in {"LIVE", "TAMPERED_ARTIFACT"}:
            return _error(400, "INVALID_PROOF_SELECTION", "proof must be LIVE or TAMPERED_ARTIFACT")
        return jsonify(_live_integrity(proof))
    except (KeyError, OSError) as exc:
        return _error(503, "RECEIPT_PROOF_UNAVAILABLE", str(exc))


@app.get("/")
def stage11_index():
    if not (STAGE11_FRONTEND / "index.html").exists():
        return _error(404, "JUDGE_INTERFACE_NOT_BUILT", "frontend bundle is unavailable")
    return app.send_static_file("index.html")


@app.get("/health")
def health():
    return {"status": "ok", "service": "isopact-outcome-gateway", "region": "africa-south1"}
