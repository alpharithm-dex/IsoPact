from __future__ import annotations

import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
PROJECT = "isopact-agentic-20260823"
PROJECT_NUMBER = "442539309409"
LOCATION = "europe-west1"
GATEWAY_ID = "isopact-egress"
REGISTRY = f"//agentregistry.googleapis.com/projects/{PROJECT}/locations/{LOCATION}"
TARGET_URL = "https://isopact-outcome-gateway-442539309409.africa-south1.run.app"
GCLOUD = r"C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"


def token() -> str:
    return subprocess.check_output([GCLOUD, "auth", "print-access-token"], text=True).strip()


def call(method: str, url: str, **kwargs):
    headers = dict(kwargs.pop("headers", {}))
    headers["Authorization"] = f"Bearer {token()}"
    return requests.request(method, url, headers=headers, timeout=60, **kwargs)


def wait_operation(base: str, operation: dict) -> dict:
    if operation.get("done"):
        return operation
    for _ in range(120):
        response = call("GET", f"{base}/v1/{operation['name']}")
        response.raise_for_status()
        result = response.json()
        if result.get("done"):
            return result
        time.sleep(3)
    raise TimeoutError(operation["name"])


def ensure_endpoint(proof: dict) -> str | None:
    base = "https://agentregistry.googleapis.com"
    parent = f"projects/{PROJECT_NUMBER}/locations/{LOCATION}"
    service_id = "isopact-outcome-gateway-egress"
    service_url = f"{base}/v1alpha/{parent}/services/{service_id}"
    current = call("GET", service_url)
    if current.status_code == 404:
        created = call("POST", f"{base}/v1alpha/{parent}/services", params={"serviceId": service_id}, json={
            "displayName": "IsoPact Outcome Gateway Egress Target",
            "description": "europe-west1 registry target for the africa-south1 IsoPact settlement plane.",
            "interfaces": [{"url": TARGET_URL, "protocolBinding": "HTTP_JSON"}],
            "endpointSpec": {"type": "NO_SPEC"},
        })
        if not created.ok:
            proof["endpoint"] = {"status": "FAILED", "http_status": created.status_code, "error": created.text}
            return None
        proof["endpoint_create_operation"] = wait_operation(base, created.json())
        current = call("GET", service_url)
    if not current.ok:
        proof["endpoint"] = {"status": "FAILED", "http_status": current.status_code, "error": current.text}
        return None
    proof["endpoint"] = {"status": "REGISTERED", "service": current.json()}
    return current.json().get("registryResource")


def main() -> int:
    proof = {
        "generated_at": datetime.now(UTC).isoformat(),
        "project": PROJECT,
        "location": LOCATION,
        "requested_mode": "AGENT_TO_ANYWHERE",
        "registry": REGISTRY,
        "target": TARGET_URL,
    }
    endpoint_resource = ensure_endpoint(proof)
    base = "https://networkservices.googleapis.com"
    gateway_name = f"projects/{PROJECT}/locations/{LOCATION}/agentGateways/{GATEWAY_ID}"
    current = call("GET", f"{base}/v1/{gateway_name}")
    if current.status_code == 404:
        created = call("POST", f"{base}/v1/projects/{PROJECT}/locations/{LOCATION}/agentGateways", params={"agentGatewayId": GATEWAY_ID}, json={
            "description": "IsoPact Agent Runtime default-deny egress governance gateway.",
            "googleManaged": {"governedAccessPath": "AGENT_TO_ANYWHERE"},
            "registries": [REGISTRY],
            "labels": {"system": "isopact", "stage": "8b"},
        })
        proof["create_http_status"] = created.status_code
        if not created.ok:
            proof.update({
                "project_access": False,
                "status": "PRODUCT_ACCESS_UNAVAILABLE",
                "exact_reason": created.text,
                "resource": None,
                "endpoint_resource": endpoint_resource,
            })
        else:
            proof["create_operation"] = wait_operation(base, created.json())
            current = call("GET", f"{base}/v1/{gateway_name}")
    if current.ok:
        proof.update({
            "project_access": True,
            "status": "CREATED_DEFAULT_DENY_NOT_BOUND",
            "resource": current.json(),
            "endpoint_resource": endpoint_resource,
            "mode": "AGENT_TO_ANYWHERE",
            "identity_policy": "DEFAULT_DENY; NO roles/iap.egressor destination grant",
            "denied_flow_proof": "No destination identity binding exists, so the documented iap.webServiceVersions.egressViaIAP permission is absent and egress is denied by default.",
            "runtime_binding": "NOT_APPLIED",
            "runtime_binding_reason": (
                "A safe existing-agent binding redirects all Runtime egress and requires the complete IAP authz extension plus explicit LLM, Registry, telemetry, Sessions/Memory and destination allowlists. "
                "The installed gcloud 553.0.0 iap web commands also do not yet accept the documented agent-registry resource type. Binding the canonical fleet would therefore risk breaking its proven operation."
            ),
            "integration_claimed": False,
        })
    output = ROOT / "artifacts" / "agents" / "agent-gateway-probe.json"
    output.write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print(json.dumps({key: proof.get(key) for key in ("project_access", "status", "resource", "endpoint_resource", "identity_policy", "exact_reason")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
