from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT = "isopact-agentic-20260823"
LOCATION = "europe-west1"
STAGING_BUCKET = "gs://isopact-agentic-20260823-agent-runtime"
REQUIREMENTS = [
    "google-adk[a2a]==2.7.1",
    "google-cloud-aiplatform[agent_engines,adk]==1.165.1",
    "a2a-sdk==1.1.2",
    "cloudpickle==3.1.2",
    "pydantic==2.13.4",
    "google-cloud-firestore==2.21.0",
    "requests==2.32.5",
]


def _jsonable(value):
    api_resource = getattr(value, "api_resource", None)
    if api_resource is not None and hasattr(api_resource, "model_dump"):
        resource = api_resource.model_dump(mode="json", exclude_none=True)
        # Class-method schemas and GCS staging internals are noisy and are not
        # endpoint/identity evidence. Keep only the deployment proof fields.
        spec = resource.get("spec", {})
        return {
            "name": resource.get("name"),
            "display_name": resource.get("display_name"),
            "description": resource.get("description"),
            "create_time": resource.get("create_time"),
            "update_time": resource.get("update_time"),
            "agent_framework": spec.get("agent_framework"),
            "identity_type": spec.get("identity_type"),
            "effective_identity": spec.get("effective_identity"),
            "deployment_spec": spec.get("deployment_spec"),
        }
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return {"repr": repr(value)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy the specialized IsoPact ADK fleet.")
    parser.add_argument(
        "--roles",
        nargs="+",
        default=["SUPPORT", "FULFILLMENT", "RETENTION", "RESOLVER"],
        choices=["SUPPORT", "FULFILLMENT", "RETENTION", "RESOLVER"],
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    source_root = root / "src"
    sys.path.insert(0, str(source_root))

    from agentplatform import Client, agent_engines, types
    from isopact.agents.fleet import IDENTITIES, build_deployment_agent
    from isopact.agents.models import AgentRole

    # extra_packages preserves its input path in the deployment archive. Running
    # from src makes the archive member `isopact/`, which is importable remotely.
    os.chdir(source_root)
    client = Client(project=PROJECT, location=LOCATION)
    output_path = root / "artifacts" / "agents" / "runtime-deployments.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    evidence = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": PROJECT,
        "location": LOCATION,
        "staging_bucket": STAGING_BUCKET,
        "managed_identity_requested": True,
        "deployments": [],
    }

    for role_name in args.roles:
        role = AgentRole(role_name)
        app = agent_engines.AdkApp(app=build_deployment_agent(role), enable_tracing=True)
        try:
            remote = client.agent_engines.create(
                agent=app,
                config={
                    "staging_bucket": STAGING_BUCKET,
                    "requirements": REQUIREMENTS,
                    "extra_packages": ["isopact"],
                    "display_name": f"IsoPact {role.value.title()} Agent v1",
                    "description": (
                        f"Specialized {role.value.lower()} worker; "
                        f"skill={IDENTITIES[role].skill_id}; consequential requests route through IsoPact."
                    ),
                    "identity_type": types.IdentityType.AGENT_IDENTITY,
                    "env_vars": {
                        "GOOGLE_GENAI_USE_VERTEXAI": "true",
                        # The runtime is regional; gemini-3.5-flash is verified
                        # for this project through Vertex's global endpoint.
                        "GOOGLE_CLOUD_LOCATION": "global",
                    },
                    "min_instances": 0,
                    "max_instances": 2,
                },
            )
            record = {
                "role": role.value,
                "logical_agent_id": IDENTITIES[role].agent_id,
                "skill_id": IDENTITIES[role].skill_id,
                "status": "DEPLOYED",
                "resource": _jsonable(remote),
            }
        except Exception as exc:  # Persist partial progress and exact API result.
            record = {
                "role": role.value,
                "logical_agent_id": IDENTITIES[role].agent_id,
                "skill_id": IDENTITIES[role].skill_id,
                "status": "FAILED",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            evidence["deployments"].append(record)
            output_path.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
            print(json.dumps(record, indent=2, default=str), flush=True)
            return 1
        evidence["deployments"].append(record)
        output_path.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
        print(json.dumps(record, indent=2, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
