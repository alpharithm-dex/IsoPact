from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    source_root = root / "src"
    sys.path.insert(0, str(source_root))
    os.chdir(source_root)

    import vertexai
    from agentplatform import Client, types
    from isopact.agents.fleet import build_support_a2a_agent

    project = "isopact-agentic-20260823"
    location = "europe-west1"
    # The A2A card must advertise the actual regional runtime URL. The ADK
    # executor configures its Gemini client explicitly for Vertex global.
    vertexai.init(project=project, location=location)
    local = build_support_a2a_agent()
    remote = Client(project=project, location=location).agent_engines.create(
        agent=local,
        config={
            "staging_bucket": "gs://isopact-agentic-20260823-agent-runtime",
            "requirements": [
                "google-adk[a2a]==2.7.1",
                "google-cloud-aiplatform[agent_engines,adk]==1.165.1",
                "a2a-sdk==1.1.2",
                "cloudpickle==3.1.2",
                "pydantic==2.13.4",
                "requests==2.32.5",
                "sse-starlette==3.4.8",
            ],
            "extra_packages": ["isopact"],
            "display_name": "IsoPact Support Agent A2A v1",
            "description": "A2A Support agent; skill=resolve_missing_order_financially; IsoPact Gateway only.",
            "identity_type": types.IdentityType.AGENT_IDENTITY,
            "env_vars": {"GOOGLE_GENAI_USE_VERTEXAI": "true", "GOOGLE_CLOUD_LOCATION": "global"},
            "agent_server_mode": types.AgentServerMode.EXPERIMENTAL,
            "min_instances": 0,
            "max_instances": 2,
        },
    )
    resource = remote.api_resource.model_dump(mode="json", exclude_none=True)
    evidence = {
        "name": resource.get("name"),
        "display_name": resource.get("display_name"),
        "agent_card": resource.get("spec", {}).get("agent_card"),
        "identity_type": resource.get("spec", {}).get("identity_type"),
        "effective_identity": resource.get("spec", {}).get("effective_identity"),
        "agent_server_mode": resource.get("spec", {}).get("deployment_spec", {}).get("agent_server_mode"),
    }
    path = root / "artifacts" / "agents" / "support-a2a-deployment.json"
    path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
