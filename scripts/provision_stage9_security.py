from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from google.cloud import modelarmor_v1
import google.auth
from google.auth import impersonated_credentials

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "isopact-agentic-20260823"
LOCATION = "europe-west1"
TEMPLATE_ID = "isopact-untrusted-input-v1"
SCREENER_SA = "isopact-model-input-screener@isopact-agentic-20260823.iam.gserviceaccount.com"


def main() -> int:
    source, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    delegated = impersonated_credentials.Credentials(
        source_credentials=source,
        target_principal=SCREENER_SA,
        target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
        lifetime=900,
    )
    client = modelarmor_v1.ModelArmorClient(
        credentials=delegated,
        transport="rest",
        client_options={"api_endpoint": f"modelarmor.{LOCATION}.rep.googleapis.com"},
    )
    parent = f"projects/{PROJECT}/locations/{LOCATION}"
    name = f"{parent}/templates/{TEMPLATE_ID}"
    try:
        template = client.get_template(request={"name": name})
        created = False
    except Exception as exc:
        if "404" not in str(exc) and "not found" not in str(exc).lower():
            raise
        template = client.create_template(request={
            "parent": parent,
            "template_id": TEMPLATE_ID,
            "template": modelarmor_v1.Template(filter_config=modelarmor_v1.FilterConfig(
                pi_and_jailbreak_filter_settings=modelarmor_v1.PiAndJailbreakFilterSettings(
                    filter_enforcement=1,
                    confidence_level=modelarmor_v1.DetectionConfidenceLevel.LOW_AND_ABOVE,
                ),
                malicious_uri_filter_settings=modelarmor_v1.MaliciousUriFilterSettings(
                    filter_enforcement=1,
                ),
            )),
        })
        created = True
    proof = {
        "generated_at": datetime.now(UTC).isoformat(),
        "project": PROJECT,
        "region": LOCATION,
        "template": modelarmor_v1.Template.to_dict(template),
        "created": created,
        "filters": ["PROMPT_INJECTION_AND_JAILBREAK_LOW_AND_ABOVE", "MALICIOUS_URI"],
        "security_boundary": "untrusted text before Gemini only",
    }
    output = ROOT / "artifacts" / "security" / "model-armor-template.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print(json.dumps(proof, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
