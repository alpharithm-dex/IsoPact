from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path


PROJECT = "isopact-agentic-20260823"
LOCATION = "europe-west1"
STAGING_BUCKET = "gs://isopact-agentic-20260823-agent-runtime"
GATEWAY_URL = "https://isopact-outcome-gateway-442539309409.africa-south1.run.app"
RESOURCES = {
    "SUPPORT": "projects/442539309409/locations/europe-west1/reasoningEngines/1997126532413259776",
    "FULFILLMENT": "projects/442539309409/locations/europe-west1/reasoningEngines/7471674091947163648",
    "RETENTION": "projects/442539309409/locations/europe-west1/reasoningEngines/1103584218845282304",
    "RESOLVER": "projects/442539309409/locations/europe-west1/reasoningEngines/4435825730634383360",
}
REQUIREMENTS = [
    "google-adk[a2a]==2.7.1",
    "google-cloud-aiplatform[agent_engines,adk]==1.165.1",
    "a2a-sdk==1.1.2",
    "cloudpickle==3.1.2",
    "pydantic==2.13.4",
    "google-auth==2.49.1",
    "requests==2.32.5",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--roles", nargs="+", choices=sorted(RESOURCES), default=sorted(RESOURCES))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    from agentplatform import Client, agent_engines
    from isopact.agents.fleet import build_deployment_agent
    from isopact.agents.models import AgentRole

    os.chdir(root / "src")
    client = Client(project=PROJECT, location=LOCATION)
    output = root / "artifacts" / "agents" / "stage8b-runtime-updates.json"
    evidence = {
        "generated_at": datetime.now(UTC).isoformat(),
        "project": PROJECT,
        "location": LOCATION,
        "gateway_url": GATEWAY_URL,
        "updates": [],
    }
    for role_name in args.roles:
        resource = RESOURCES[role_name]
        role = AgentRole(role_name)
        # Do not pass the deprecated enable_tracing=True flag: Agent Runtime's
        # ADK template otherwise forces legacy message capture on at startup.
        # The deployment-wide telemetry env flag enables tracing safely.
        app = agent_engines.AdkApp(app=build_deployment_agent(role))
        try:
            updated = client.agent_engines.update(
                name=resource,
                agent=app,
                config={
                    "staging_bucket": STAGING_BUCKET,
                    "requirements": REQUIREMENTS,
                    "extra_packages": ["isopact"],
                    "env_vars": {
                        "GOOGLE_GENAI_USE_VERTEXAI": "true",
                        "GOOGLE_CLOUD_LOCATION": "global",
                        "ISOPACT_OUTCOME_GATEWAY_URL": GATEWAY_URL,
                        "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true",
                        "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental",
                        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "NO_CONTENT",
                        "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS": "false",
                        # Prevent invocation-supplied RunConfig telemetry values
                        # from overriding the deployment-wide privacy policy.
                        "ADK_TELEMETRY_IGNORE_RUN_CONFIG": "true",
                    },
                    "min_instances": 0,
                    "max_instances": 2,
                },
            )
            api = updated.api_resource.model_dump(mode="json", exclude_none=True)
            record = {
                "role": role.value,
                "name": api.get("name"),
                "display_name": api.get("display_name"),
                "update_time": api.get("update_time"),
                "identity_type": api.get("spec", {}).get("identity_type"),
                "effective_identity": api.get("spec", {}).get("effective_identity"),
                "status": "UPDATED",
            }
        except Exception as exc:
            record = {
                "role": role.value,
                "name": resource,
                "status": "FAILED",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            evidence["updates"].append(record)
            output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(json.dumps(record, indent=2), flush=True)
            return 1
        evidence["updates"].append(record)
        output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(record, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
