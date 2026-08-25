from __future__ import annotations

import json
import re
import subprocess
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "isopact-agentic-20260823"


def gcloud(*args: str):
    executable = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if not executable:
        raise RuntimeError("gcloud executable not found")
    result = subprocess.run([executable, *args, "--format=json"], check=True, capture_output=True, text=True)
    return json.loads(result.stdout or "{}")


def bindings_for(policy: dict, principal: str) -> list[str]:
    member = "serviceAccount:" + principal
    return sorted(item["role"] for item in policy.get("bindings", []) if member in item.get("members", []))


def main() -> None:
    project_policy = gcloud("projects", "get-iam-policy", PROJECT)
    key_policy = gcloud(
        "kms", "keys", "get-iam-policy", "isopact-provenance-signing",
        "--keyring=isopact-settlement-security", "--location=africa-south1", f"--project={PROJECT}",
    )
    secret_policy = gcloud(
        "secrets", "get-iam-policy", "isopact-stripe-webhook-signing-secret", f"--project={PROJECT}",
    )
    identities = {
        "Outcome Gateway": f"isopact-outcome-gateway@{PROJECT}.iam.gserviceaccount.com",
        "Evidence ingestor": f"isopact-evidence-ingestor@{PROJECT}.iam.gserviceaccount.com",
        "Checkpoint signer": f"isopact-checkpoint-signer@{PROJECT}.iam.gserviceaccount.com",
        "Model input screener": f"isopact-model-input-screener@{PROJECT}.iam.gserviceaccount.com",
    }
    reviewed = {
        label: {
            "principal": principal,
            "project_roles": bindings_for(project_policy, principal),
            "kms_key_roles": bindings_for(key_policy, principal),
            "secret_roles": bindings_for(secret_policy, principal),
        }
        for label, principal in identities.items()
    }
    runtime_resources = {
        "Support Agent": "projects/442539309409/locations/europe-west1/reasoningEngines/1997126532413259776",
        "Fulfillment Agent": "projects/442539309409/locations/europe-west1/reasoningEngines/7471674091947163648",
        "Retention Agent": "projects/442539309409/locations/europe-west1/reasoningEngines/1103584218845282304",
        "Resolver Agent": "projects/442539309409/locations/europe-west1/reasoningEngines/4435825730634383360",
    }
    key_members = sorted({member for item in key_policy.get("bindings", []) for member in item.get("members", [])})
    broad_service_roles = []
    for item in project_policy.get("bindings", []):
        if item["role"] in {"roles/owner", "roles/editor"}:
            for member in item.get("members", []):
                if member.startswith("serviceAccount:"):
                    broad_service_roles.append({"member": member, "role": item["role"]})
    credential_patterns = re.compile(r"(?i)(-----BEGIN (RSA |EC )?PRIVATE KEY-----|AIza[0-9A-Za-z_-]{30,}|sk_(live|test)_[0-9A-Za-z]{16,}|whsec_[0-9A-Za-z]{16,})")
    matches = []
    excluded = {".git", ".venv", ".venv-win", "__pycache__", "artifacts", "work", "outputs"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in excluded for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if credential_patterns.search(text):
            matches.append(str(path.relative_to(ROOT)))
    proof = {
        "project": PROJECT,
        "service_identities": reviewed,
        "agent_runtime_resources": runtime_resources,
        "agent_kms_signing_permission": any(any(resource in member for member in key_members) for resource in runtime_resources.values()),
        "kms_key_members": key_members,
        "broad_service_roles": broad_service_roles,
        "flagged_existing_broad_role": broad_service_roles,
        "human_owner_editor_roles_not_revoked": True,
        "committed_credential_matches": sorted(matches),
        "secret_boundary": {
            "secret": "Stripe-shaped webhook HMAC key in Secret Manager; evidence ingestor only",
            "configuration": ["project ID", "regions", "service URLs", "KMS resource names", "Model Armor template name", "public keys"],
        },
    }
    proof["status"] = "PASS_WITH_EXISTING_ROLE_FLAG" if not proof["agent_kms_signing_permission"] and not matches else "FAIL"
    output = ROOT / "artifacts" / "security" / "iam-audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(proof, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
