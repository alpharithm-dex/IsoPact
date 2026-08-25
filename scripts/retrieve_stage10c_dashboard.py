from __future__ import annotations

import argparse
import json
from pathlib import Path

import google.auth
from google.auth.transport.requests import AuthorizedSession


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "observability" / "dashboard.json"
REQUIRED = {
    "Gateway decisions",
    "Conflict prevention",
    "Settlement transitions",
    "Evidence processing",
    "Invariant failures",
    "Compensation outcomes",
    "Gateway latency p95",
    "Claim append latency p95",
    "Resolver latency p95",
    "KMS signing latency p95",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-number", required=True)
    parser.add_argument("--dashboard", required=True)
    args = parser.parse_args()
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    session = AuthorizedSession(credentials)
    name = f"projects/{args.project_number}/dashboards/{args.dashboard}"
    response = session.get(
        f"https://monitoring.googleapis.com/v1/{name}", timeout=30
    )
    response.raise_for_status()
    dashboard = response.json()
    titles = {
        tile.get("widget", {}).get("title")
        for tile in dashboard.get("mosaicLayout", {}).get("tiles", [])
    }
    result = {
        "source": "LIVE_CLOUD_MONITORING_DASHBOARD",
        "deployedResource": name,
        "displayName": dashboard.get("displayName"),
        "etag": dashboard.get("etag"),
        "panelCount": len(titles),
        "panels": sorted(title for title in titles if title),
        "missingPanels": sorted(REQUIRED - titles),
        "result": "PASS" if REQUIRED <= titles else "BLOCKED",
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
