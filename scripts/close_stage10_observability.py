from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "observability"

REQUIRED = (
    "privacy-canary.json", "primary-protected-trace.json", "trace-completeness.json",
    "log-correlation.json", "metrics-proof.json", "dashboard.json",
    "reconciliation-trace.json", "toctou-trace.json", "outcome-unknown-trace.json",
    "latency-waterfall.json", "telemetry-overhead.json", "privacy-audit.json", "claim-contention.json",
)


def load(name: str):
    path = OUT / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def main() -> int:
    privacy = load("privacy-canary.json") or {}
    metrics = load("metrics-proof.json") or {}
    logs = load("log-correlation.json") or {}
    completeness = load("trace-completeness.json") or {}
    checks = {
        "all_required_artifacts": all((OUT / name).exists() for name in REQUIRED),
        "privacy_canary_absent": privacy.get("result") == "PASS",
        "primary_custom_trace_live": completeness.get("result") == "PASS",
        "trace_log_correlation": logs.get("result") == "PASS",
        "representative_metrics_live": metrics.get("result") == "PASS_REPRESENTATIVE",
        "dashboard_live": bool((load("dashboard.json") or {}).get("deployedResource")),
        "reconciliation_live_complete": (load("reconciliation-trace.json") or {}).get("result") == "PASS",
        "toctou_live_complete": (load("toctou-trace.json") or {}).get("result") == "PASS",
        "outcome_unknown_live_complete": (load("outcome-unknown-trace.json") or {}).get("result") == "PASS",
        "overhead_measured": (load("telemetry-overhead.json") or {}).get("result") == "PASS",
    }
    report = {"status": "PASS" if all(checks.values()) else "BLOCKED", "checks": checks,
              "missing": [name for name in REQUIRED if not (OUT / name).exists()]}
    (OUT / "stage10b-gate.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
