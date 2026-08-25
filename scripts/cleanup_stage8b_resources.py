from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from agentplatform import Client

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "isopact-agentic-20260823"
LOCATION = "europe-west1"
CANONICAL = {
    "projects/442539309409/locations/europe-west1/reasoningEngines/1997126532413259776",
    "projects/442539309409/locations/europe-west1/reasoningEngines/7471674091947163648",
    "projects/442539309409/locations/europe-west1/reasoningEngines/1103584218845282304",
    "projects/442539309409/locations/europe-west1/reasoningEngines/4435825730634383360",
}
OBSOLETE = {
    "projects/442539309409/locations/europe-west1/reasoningEngines/8176065221165580288",
    "projects/442539309409/locations/europe-west1/reasoningEngines/2859988073519775744",
    "projects/442539309409/locations/europe-west1/reasoningEngines/3755782186901438464",
    "projects/442539309409/locations/europe-west1/reasoningEngines/378504678838632448",
}
GCLOUD = r"C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"


def main() -> int:
    client = Client(project=PROJECT, location=LOCATION)
    before = {item.api_resource.name for item in client.agent_engines.list()}
    if not CANONICAL.issubset(before):
        raise RuntimeError(f"canonical resource missing before cleanup: {sorted(CANONICAL - before)}")
    unexpected_before = before - CANONICAL - OBSOLETE
    if unexpected_before:
        raise RuntimeError(f"unexpected resource set; refusing cleanup: {sorted(unexpected_before)}")

    removed = []
    for resource in sorted(OBSOLETE & before):
        client.agent_engines.delete(name=resource, force=True)
        removed.append(resource)

    subprocess.run([
        GCLOUD, "run", "services", "delete", "isopact-pact-status",
        f"--project={PROJECT}", "--region=africa-south1", "--quiet",
    ], check=True)

    after = {item.api_resource.name for item in client.agent_engines.list()}
    proof = {
        "generated_at": datetime.now(UTC).isoformat(),
        "inventory_before": sorted(before),
        "verified_canonical_before_delete": sorted(CANONICAL),
        "removed_runtime_resources": removed,
        "removed_cloud_run_services": ["isopact-pact-status"],
        "canonical_runtime_agents_remaining": sorted(CANONICAL & after),
        "unexpected_resources_remaining": sorted(after - CANONICAL),
        "deletion_scope": "exact resource names only; historical evidence retained",
    }
    output = ROOT / "artifacts" / "agents" / "resource-cleanup.json"
    output.write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print(json.dumps(proof, indent=2))
    return 0 if after == CANONICAL else 1


if __name__ == "__main__":
    raise SystemExit(main())
