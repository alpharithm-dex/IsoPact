from __future__ import annotations

import hashlib
import json
import subprocess
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "release"
PROJECT = "isopact-agentic-20260823"


COMMANDS: dict[str, list[str]] = {
    "cloud_run_services": ["gcloud", "run", "services", "list", "--project", PROJECT, "--platform", "managed", "--format=json"],
    "cloud_run_revisions": ["gcloud", "run", "revisions", "list", "--project", PROJECT, "--region", "africa-south1", "--format=json"],
    "cloud_run_jobs": ["gcloud", "run", "jobs", "list", "--project", PROJECT, "--region", "africa-south1", "--format=json"],
    "firestore": ["gcloud", "firestore", "databases", "list", "--project", PROJECT, "--format=json"],
    "pubsub_topics": ["gcloud", "pubsub", "topics", "list", "--project", PROJECT, "--format=json"],
    "pubsub_subscriptions": ["gcloud", "pubsub", "subscriptions", "list", "--project", PROJECT, "--format=json"],
    "kms_keyrings": ["gcloud", "kms", "keyrings", "list", "--project", PROJECT, "--location", "africa-south1", "--format=json"],
    "kms_keys": ["gcloud", "kms", "keys", "list", "--project", PROJECT, "--location", "africa-south1", "--keyring", "isopact-settlement-security", "--format=json"],
    "kms_versions": ["gcloud", "kms", "keys", "versions", "list", "--project", PROJECT, "--location", "africa-south1", "--keyring", "isopact-settlement-security", "--key", "isopact-provenance-signing", "--format=json"],
    "secrets": ["gcloud", "secrets", "list", "--project", PROJECT, "--format=json"],
    "dashboards": ["gcloud", "monitoring", "dashboards", "list", "--project", PROJECT, "--format=json"],
    "service_accounts": ["gcloud", "iam", "service-accounts", "list", "--project", PROJECT, "--format=json"],
    "project_iam": ["gcloud", "projects", "get-iam-policy", PROJECT, "--format=json"],
    "artifact_repositories": ["gcloud", "artifacts", "repositories", "list", "--project", PROJECT, "--location", "africa-south1", "--format=json"],
    "artifact_images": ["gcloud", "artifacts", "docker", "images", "list", f"africa-south1-docker.pkg.dev/{PROJECT}/cloud-run-source-deploy", "--include-tags", "--format=json"],
    "enabled_apis": ["gcloud", "services", "list", "--enabled", "--project", PROJECT, "--format=json"],
}


def run(command: list[str]) -> dict[str, Any]:
    if command[0] == "gcloud":
        command = [shutil.which("gcloud.cmd") or shutil.which("gcloud") or "gcloud", *command[1:]]
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        return {"status": "UNAVAILABLE", "error": result.stderr.strip()[:1200], "command": command[:-1]}
    try:
        return {"status": "OK", "items": json.loads(result.stdout or "[]")}
    except json.JSONDecodeError:
        return {"status": "PARSE_ERROR", "output": result.stdout[:1200], "command": command[:-1]}


def resource_name(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item)
    meta = item.get("metadata") or {}
    return str(item.get("name") or meta.get("name") or item.get("serviceConfig", {}).get("service") or "unnamed")


def classify(group: str, name: str) -> tuple[str, bool, str]:
    value = name.lower()
    canonical_markers = ["isopact-outcome-gateway", "isopact-stage5-evidence", "stateclaim-signing",
                         "isopact-stage9", "isopact-stage10", "isopact-support", "isopact-fulfillment",
                         "isopact-retention", "isopact-resolver", "commerce-missing-order"]
    if any(marker in value for marker in canonical_markers) and "proof" not in value:
        return "CANONICAL", True, "active IsoPact deployment/evidence dependency"
    if "proof" in value or group in {"cloud_run_revisions", "artifact_images"}:
        return "PROOF/TEST", False, "retained reproducibility or historic verification resource"
    if group in {"enabled_apis", "project_iam", "service_accounts", "artifact_repositories"}:
        return "OPTIONAL", False, "project-level supporting inventory"
    return "OPTIONAL", False, "live project resource; not required by canonical manifest"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    raw = {group: run(command) for group, command in COMMANDS.items()}
    try:
        from google.cloud import aiplatform
        from vertexai import agent_engines
        aiplatform.init(project=PROJECT, location="europe-west1")
        agents = []
        for item in agent_engines.list():
            agents.append({"name": item.resource_name, "display_name": getattr(item, "display_name", None)})
        raw["reasoning_engines"] = {"status": "OK", "items": agents, "query": "Vertex AI SDK live list"}
    except Exception as exc:
        raw["reasoning_engines"] = {"status": "UNAVAILABLE", "error": f"{type(exc).__name__}: {exc}"[:1200]}
    try:
        from google.cloud import modelarmor_v1
        client = modelarmor_v1.ModelArmorClient(client_options={"api_endpoint": "modelarmor.europe-west1.rep.googleapis.com"})
        items = [{"name": item.name} for item in client.list_templates(parent=f"projects/{PROJECT}/locations/europe-west1")]
        raw["model_armor"] = {"status": "OK", "items": items, "query": "Model Armor SDK live list"}
    except Exception as exc:
        raw["model_armor"] = {"status": "UNAVAILABLE", "error": f"{type(exc).__name__}: {exc}"[:1200]}
    resources = []
    for group, result in raw.items():
        for item in result.get("items", []) if isinstance(result.get("items"), list) else []:
            name = resource_name(item)
            classification, canonical, reason = classify(group, name)
            resources.append({"type": group, "name": name, "region": item.get("location") if isinstance(item, dict) else None,
                              "purpose": reason, "classification": classification, "canonical": canonical,
                              "service_identity": (item.get("spec", {}).get("template", {}).get("spec", {}).get("serviceAccountName")
                                                   if isinstance(item, dict) else None),
                              "exposure": "public-network/application-auth" if "outcome-gateway" in name else "platform-managed"})
    inventory = {"schema_version": "stage13-cloud-inventory-v1", "queried_at": datetime.now(UTC).isoformat(),
                 "project": PROJECT, "resources": resources, "unknown_resources": 0,
                 "query_status": {key: value["status"] for key, value in raw.items()}}
    encoded = json.dumps(inventory, indent=2, sort_keys=True) + "\n"
    (OUT / "cloud-resources.json").write_text(encoded, encoding="utf-8")
    (OUT / "cloud-inventory-raw.json").write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"resources": len(resources), "unknown": 0, "query_status": inventory["query_status"],
                      "sha256": hashlib.sha256(encoded.encode()).hexdigest()}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
