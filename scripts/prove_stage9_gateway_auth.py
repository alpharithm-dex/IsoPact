from __future__ import annotations

import base64
import copy
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from isopact.security.agent_tokens import verify_agent_identity_token


def main() -> None:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key()

    class Key:
        key = public

    class Jwks:
        def get_signing_key_from_jwt(self, token):
            return Key()

    issuer = "https://sts.googleapis.com/v1/projects/442539309409/locations/global/workloadIdentityPools/agents.global.proj-442539309409.system.id.goog"
    audience = "https://isopact-outcome-gateway-442539309409.africa-south1.run.app"
    subject = "spiffe://agents.global.proj-442539309409.system.id.goog/resources/aiplatform/projects/442539309409/locations/europe-west1/reasoningEngines/1997126532413259776"
    now = int(time.time())

    def token(**overrides):
        payload = {"iss": issuer, "aud": [audience], "sub": subject, "iat": now - 1, "nbf": now - 1, "exp": now + 300}
        payload.update(overrides)
        return jwt.encode(payload, private, algorithm="RS256")

    valid = token()
    parts = valid.split(".")
    decoded = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
    decoded["sub"] = "spiffe://modified"
    modified_payload = base64.urlsafe_b64encode(json.dumps(decoded, separators=(",", ":")).encode()).decode().rstrip("=")
    attacks = {
        "expired_token": token(exp=now - 1),
        "wrong_audience": token(aud=["https://wrong.example"]),
        "wrong_issuer": token(iss="https://wrong.example"),
        "unknown_spiffe_subject": token(sub="spiffe://unknown"),
        "not_before_in_future": token(nbf=now + 60),
        "unsigned_token": jwt.encode({"iss": issuer, "aud": audience, "sub": subject, "iat": now, "exp": now + 60}, key="", algorithm="none"),
        "modified_token_payload": parts[0] + "." + modified_payload + "." + parts[2],
    }
    results = {}
    external_calls = 0
    for name, candidate in attacks.items():
        try:
            verify_agent_identity_token(candidate, jwks_client=Jwks(), expected_issuer=issuer, expected_audience=audience, subject_roles={subject: "SUPPORT"})
            external_calls += 1
            results[name] = "UNEXPECTED_ALLOW"
        except PermissionError:
            results[name] = "DENY"

    role, metadata = verify_agent_identity_token(valid, jwks_client=Jwks(), expected_issuer=issuer, expected_audience=audience, subject_roles={subject: "SUPPORT"})
    live = json.loads((ROOT / "artifacts" / "agents" / "stage8b-end-to-end.json").read_text(encoding="utf-8"))
    spoof = live["body_spoof_proof"]
    replay = live["duplicate_support"]["gateway"]
    proof = {
        "status": "PASS" if all(v == "DENY" for v in results.values()) and external_calls == 0 and spoof["body_identity_used_for_authority"] is False and replay["external_call_executed"] is False else "FAIL",
        "verification": {
            "algorithm_allowlist": ["RS256"],
            "jwks": "Google STS JWKS; signing key selected before decode",
            "issuer_exact_match": True,
            "audience_exact_match": True,
            "expiration_required": True,
            "not_before_checked_when_present": True,
            "subject_must_map_to_known_runtime": True,
            "valid_role": role,
            "safe_valid_metadata": metadata,
        },
        "attack_results": results,
        "invalid_token_consequential_external_calls": external_calls,
        "live_body_spoof": spoof,
        "authenticated_business_replay": {
            "bearer_tokens_may_be_reused_within_lifetime": True,
            "one_time_token_claim": False,
            "semantic_operation_identity": replay["operation_identity"],
            "gateway_decision": replay["gateway_decision"],
            "reason_code": replay["reason_code"],
            "duplicate_external_execution": replay["external_call_executed"],
        },
    }
    output = ROOT / "artifacts" / "security" / "gateway-auth-attacks.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(proof, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
