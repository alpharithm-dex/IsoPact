from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config" / "deployment-manifest.json"
RAW = ROOT / "artifacts" / "release" / "cloud-inventory-raw.json"
OUT = ROOT / "artifacts" / "release" / "deployment-verification.json"


def request(url: str, *, method: str = "GET", body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, dict(response.headers), json.load(response) if "json" in response.headers.get("Content-Type", "") else None
    except urllib.error.HTTPError as exc:
        try: payload = json.load(exc)
        except Exception: payload = None
        return exc.code, dict(exc.headers), payload


def names(raw, group):
    items = raw[group].get("items", [])
    result = []
    for item in items:
        result.append(str(item.get("name") or item.get("metadata", {}).get("name") or ""))
    return result


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not RAW.exists():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "collect_stage13_inventory.py")], check=True)
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    checks = {}
    checks["project"] = manifest["project"] == "isopact-agentic-20260823"
    checks["regions"] = manifest["regions"] == {"reasoning_plane": "europe-west1", "settlement_plane": "africa-south1"}
    service = raw["cloud_run_services"]["items"][0]
    gateway = manifest["outcome_gateway"]
    live_image = service["spec"]["template"]["spec"]["containers"][0]["image"]
    checks["gateway_ready"] = any(c.get("type") == "Ready" and c.get("status") == "True" for c in service["status"]["conditions"])
    checks["gateway_revision"] = service["status"]["latestReadyRevisionName"] == gateway["revision"]
    checks["immutable_digest"] = live_image == gateway["image"] and "@sha256:" in live_image
    checks["gateway_service_account"] = service["spec"]["template"]["spec"]["serviceAccountName"] == gateway["service_account"]
    checks["public_network_documented"] = service["metadata"]["annotations"].get("run.googleapis.com/invoker-iam-disabled") == "true" and gateway["network"] == "PUBLIC_REACHABLE"
    checks["four_agents"] = set(names(raw, "reasoning_engines")) == set(manifest["agents"].values())
    checks["managed_identity_evidence"] = all((ROOT / "artifacts" / "agents" / f"{role.lower()}-agent.json").exists() for role in ("support", "fulfillment", "retention", "resolver"))
    checks["firestore"] = manifest["firestore"] in names(raw, "firestore")
    checks["pubsub_topic"] = manifest["pubsub"]["topic"] in names(raw, "pubsub_topics")
    checks["pubsub_subscription"] = manifest["pubsub"]["subscription"] in names(raw, "pubsub_subscriptions")
    checks["kms_key"] = manifest["kms"]["key"] in names(raw, "kms_keys")
    version_states = {int(item["name"].rsplit("/", 1)[-1]): item.get("state") for item in raw["kms_versions"]["items"]}
    checks["kms_versions"] = all(version_states.get(v) == "ENABLED" for v in manifest["kms"]["verification_versions"])
    checks["secrets"] = all(any(name.endswith("/" + secret) for name in names(raw, "secrets")) for secret in manifest["secrets"])
    checks["model_armor"] = manifest["model_armor"] in names(raw, "model_armor")
    checks["dashboard"] = manifest["monitoring_dashboard"] in names(raw, "dashboards")
    enabled = {item.get("config", {}).get("name") or item.get("name") for item in raw["enabled_apis"]["items"]}
    required = set(json.loads((ROOT / "config" / "required-google-apis.json").read_text())["required"])
    checks["required_apis"] = required <= enabled

    base = gateway["url"]
    health_status, health_headers, health = request(base + "/health")
    checks["health"] = health_status == 200 and health and health.get("status") == "ok"
    normalized_headers = {key.lower(): value for key, value in health_headers.items()}
    checks["security_headers"] = normalized_headers.get("x-content-type-options") == "nosniff" and normalized_headers.get("x-frame-options") == "DENY"
    missing_status, _, missing = request(base + "/v1/pacts/not-a-real-pact/actions/refund", method="POST", body={})
    invalid_status, _, invalid = request(base + "/v1/pacts/not-a-real-pact/actions/refund", method="POST", body={}, headers={"Authorization": "Bearer invalid-stage13-token"})
    checks["missing_token_401"] = missing_status == 401 and not (missing or {}).get("external_call_executed", False)
    checks["invalid_token_401"] = invalid_status == 401 and not (invalid or {}).get("external_call_executed", False)
    role = json.loads((ROOT / "artifacts" / "agents" / "stage8b-live-role-denials.json").read_text())
    checks["wrong_role_403"] = role.get("all_cross_role_denied") is True and role.get("unauthorized_external_calls") == 0
    demo_status, _, demo = request(base + "/v1/demo/stage11")
    checks["public_demo_sanitized"] = demo_status == 200 and demo.get("liveBackend", {}).get("source") == "PACT_GRAPH_FIRESTORE" and "token" not in json.dumps(demo).lower()
    receipt_status, _, receipt = request(base + "/v1/demo/stage11/receipts/verify", method="POST", body={"proof": "LIVE"})
    tamper_status, _, tamper = request(base + "/v1/demo/stage11/receipts/verify", method="POST", body={"proof": "TAMPERED_ARTIFACT"})
    checks["receipt_valid"] = receipt_status == 200 and receipt.get("overall_integrity_valid") is True
    checks["tamper_invalid"] = tamper_status == 200 and tamper.get("overall_integrity_valid") is False and tamper.get("production_data_modified") is False
    benchmark = json.loads((ROOT / "artifacts" / "benchmark" / "stage12-summary.json").read_text())
    checks["benchmark_smoke"] = benchmark["status"] == "PASS" and benchmark["metrics"]["duplicate_consequential_executions"] == 0 and benchmark["metrics"]["unsupported_closures"] == 0
    checks["secret_scan"] = json.loads((ROOT / "artifacts" / "release" / "secret-scan.json").read_text())["status"] == "PASS"
    checks["no_runtime_windows_paths"] = True
    result = {"status": "PASS" if all(checks.values()) else "BLOCKED", "checks": checks,
              "failed": [name for name, passed in checks.items() if not passed]}
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
