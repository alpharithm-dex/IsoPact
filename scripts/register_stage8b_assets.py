from __future__ import annotations

import argparse
import base64
import io
import json
import sys
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import google.auth
from google.auth.transport.requests import AuthorizedSession


ROOT = Path(__file__).resolve().parents[1]
PROJECT_NUMBER = "442539309409"
RUNTIME_LOCATION = "europe-west1"
SKILL_LOCATION = "europe-west4"
ENDPOINT_LOCATION = "africa-south1"
CANONICAL_ENGINES = {
    "SUPPORT": "1997126532413259776",
    "FULFILLMENT": "7471674091947163648",
    "RETENTION": "1103584218845282304",
    "RESOLVER": "4435825730634383360",
}
SKILLS = {
    "resolve-missing-order-financially": "Resolve Missing Order Financially",
    "manage-replacement-fulfillment": "Manage Replacement Fulfillment",
    "apply-customer-retention-remedy": "Apply Customer Retention Remedy",
    "reconcile-outcome-conflict": "Reconcile Outcome Conflict",
}


def wait_operation(session: AuthorizedSession, operation: dict) -> dict:
    if operation.get("done"):
        return operation
    url = f"https://agentregistry.googleapis.com/v1alpha/{operation['name']}"
    for _ in range(90):
        result = session.get(url, timeout=120)
        result.raise_for_status()
        data = result.json()
        if data.get("done"):
            return data
        time.sleep(2)
    raise TimeoutError(operation["name"])


def archive(skill_id: str) -> str:
    content = (ROOT / "skills" / "registry" / skill_id / "SKILL.md").read_bytes()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("SKILL.md", content)
    return base64.b64encode(buffer.getvalue()).decode()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-skills", action="store_true")
    args = parser.parse_args()
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    session = AuthorizedSession(credentials)
    proof = {"generated_at": datetime.now(UTC).isoformat(), "runtime_agents": [], "skills": [], "endpoint": {}}

    agents_url = f"https://agentregistry.googleapis.com/v1alpha/projects/{PROJECT_NUMBER}/locations/{RUNTIME_LOCATION}/agents"
    response = session.get(agents_url, timeout=120)
    response.raise_for_status()
    for agent in response.json().get("agents", []):
        uri = agent.get("attributes", {}).get("agentregistry.googleapis.com/system/RuntimeReference", {}).get("uri", "")
        engine = uri.rsplit("/", 1)[-1]
        role = next((name for name, wanted in CANONICAL_ENGINES.items() if wanted == engine), None)
        if role:
            proof["runtime_agents"].append({
                "role": role,
                "name": agent.get("name"),
                "agent_id": agent.get("agentId"),
                "framework": agent.get("attributes", {}).get("agentregistry.googleapis.com/system/Framework", {}).get("framework"),
                "protocols": agent.get("protocols", []),
                "a2a_skills": agent.get("skills", []),
                "runtime_identity": agent.get("attributes", {}).get("agentregistry.googleapis.com/system/RuntimeIdentity", {}).get("principal"),
            })
    proof["runtime_agents"].sort(key=lambda item: item["role"])

    skill_parent = f"projects/{PROJECT_NUMBER}/locations/{SKILL_LOCATION}"
    for skill_id, display_name in ({} if args.skip_skills else SKILLS).items():
        get_url = f"https://agentregistry.googleapis.com/v1alpha/{skill_parent}/skills/{skill_id}"
        existing = session.get(get_url, timeout=120)
        if existing.status_code == 404:
            payload = {
                "displayName": display_name,
                "description": (ROOT / "skills" / "registry" / skill_id / "SKILL.md").read_text(encoding="utf-8").split("description: ", 1)[1].splitlines()[0],
                "type": "SIMPLE",
                "targetState": "TARGET_STATE_ACTIVE",
                "initialRevision": {"archiveUploadSource": {"archiveContent": archive(skill_id)}},
            }
            created = session.post(
                f"https://agentregistry.googleapis.com/v1alpha/{skill_parent}/skills",
                params={"skillId": skill_id}, json=payload, timeout=120,
            )
            if created.status_code >= 400:
                proof["skills"].append({"requested_id": skill_id, "status": "FAILED", "http_status": created.status_code, "error": created.text})
                continue
            wait_operation(session, created.json())
        elif existing.status_code >= 400:
            proof["skills"].append({"requested_id": skill_id, "status": "FAILED", "http_status": existing.status_code, "error": existing.text})
            continue
        current = session.get(get_url, timeout=120)
        revisions = session.get(f"{get_url}/revisions", timeout=120)
        proof["skills"].append({"requested_id": skill_id, "status": "REGISTERED", "resource": current.json(), "revisions": revisions.json().get("skillRevisions", revisions.json().get("revisions", []))})

    if args.skip_skills:
        proof["skill_search"] = {"http_status": None, "response": "SKIPPED_AFTER_AUTHENTICATED_LIST_TIMEOUTS_IN_us-central1_us-east5_europe-west4"}
    else:
        search = session.get(
            f"https://agentregistry.googleapis.com/v1alpha/{skill_parent}/skills:search",
            params={"query": "IsoPact"}, timeout=120,
        )
        proof["skill_search"] = {"http_status": search.status_code, "response": search.json() if search.ok else search.text}

    endpoint_parent = f"projects/{PROJECT_NUMBER}/locations/{ENDPOINT_LOCATION}"
    service_id = "isopact-outcome-gateway"
    service_url = f"https://agentregistry.googleapis.com/v1alpha/{endpoint_parent}/services/{service_id}"
    service = session.get(service_url, timeout=120)
    if service.status_code == 404:
        created = session.post(
            f"https://agentregistry.googleapis.com/v1alpha/{endpoint_parent}/services",
            params={"serviceId": service_id},
            json={
                "displayName": "IsoPact Outcome Gateway",
                "description": "Authenticated africa-south1 settlement-plane HTTP API for deterministic IsoPact actions.",
                "interfaces": [{"url": "https://isopact-outcome-gateway-442539309409.africa-south1.run.app", "protocolBinding": "HTTP_JSON"}],
                "endpointSpec": {"type": "NO_SPEC"},
            }, timeout=120,
        )
        if created.ok:
            proof["endpoint"]["create_operation"] = wait_operation(session, created.json())
        else:
            proof["endpoint"] = {"status": "FAILED", "http_status": created.status_code, "error": created.text}
    elif not service.ok:
        proof["endpoint"] = {"status": "FAILED", "http_status": service.status_code, "error": service.text}
    current_service = session.get(service_url, timeout=120)
    if current_service.ok:
        service_data = current_service.json()
        proof["endpoint"]["status"] = "REGISTERED"
        proof["endpoint"]["service"] = service_data
        if service_data.get("registryResource"):
            endpoint = session.get(f"https://agentregistry.googleapis.com/v1alpha/{service_data['registryResource']}", timeout=120)
            proof["endpoint"]["endpoint"] = endpoint.json() if endpoint.ok else {"http_status": endpoint.status_code, "error": endpoint.text}

    (ROOT / "artifacts" / "agents" / "registry-final.json").write_text(json.dumps({"generated_at": proof["generated_at"], "runtime_agents": proof["runtime_agents"], "endpoint": proof["endpoint"]}, indent=2), encoding="utf-8")
    (ROOT / "artifacts" / "agents" / "skill-registry.json").write_text(json.dumps({"generated_at": proof["generated_at"], "location": SKILL_LOCATION, "skills": proof["skills"], "search": proof["skill_search"]}, indent=2), encoding="utf-8")
    print(json.dumps({"runtime_agent_count": len(proof["runtime_agents"]), "skill_statuses": [(x["requested_id"], x["status"]) for x in proof["skills"]], "endpoint_status": proof["endpoint"].get("status"), "search_http_status": proof["skill_search"]["http_status"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
