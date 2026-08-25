from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "ui"


def write(name: str, value: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    args = parser.parse_args()
    base = args.url.rstrip("/")
    live_response = requests.get(f"{base}/v1/demo/stage11", timeout=60)
    live_response.raise_for_status()
    data = live_response.json()
    valid_response = requests.post(
        f"{base}/v1/demo/stage11/receipts/verify", json={"proof": "LIVE"}, timeout=60
    )
    valid_response.raise_for_status()
    valid = valid_response.json()
    tampered_response = requests.post(
        f"{base}/v1/demo/stage11/receipts/verify",
        json={"proof": "TAMPERED_ARTIFACT"}, timeout=60,
    )
    tampered_response.raise_for_status()
    tampered = tampered_response.json()
    protected = next(item for item in data["scenarios"] if item["id"] == "protected")
    unmanaged = next(item for item in data["scenarios"] if item["id"] == "unmanaged")
    protected_text = json.dumps(protected)
    unmanaged_text = json.dumps(unmanaged)
    checks = {
        "live_firestore_read": data.get("liveBackend", {}).get("source") == "PACT_GRAPH_FIRESTORE",
        "live_mode_no_silent_fallback": data.get("liveBackend", {}).get("silentReplayFallback") is False,
        "pact_starts_open_pending_in_replay": protected["steps"][0]["lifecycle"] in {"OPEN", "PENDING"},
        "refund_allow_visible": '"ALLOW"' in protected_text and "refund" in protected_text.lower(),
        "replacement_block_visible": "EXCLUSIVE_RESOLUTION_CONFLICT" in protected_text,
        "goodwill_visible": "$50" in protected_text,
        "duplicate_block_visible": "DUPLICATE_OPERATION" in protected_text,
        "rank4_does_not_settle": any(
            item["id"] == "agent-complete-unsettled"
            and item["lifecycle"] == "PENDING"
            and item["businessOutcome"] == "NOT SETTLED"
            for item in protected["steps"]
        ),
        "rank1_then_settled": next(i for i,s in enumerate(protected["steps"]) if s["id"] == "rank1-evidence") < next(i for i,s in enumerate(protected["steps"]) if s["id"] == "settled"),
        "unmanaged_650": "$650" in unmanaged_text,
        "unmanaged_excess_450": "$450" in unmanaged_text,
        "protected_250": "$250" in protected_text,
        "prevented_400": "$400" in protected_text,
        "never_calls_400_cash_saved": "$400 saved" not in protected_text.lower() and "cash saved" not in protected_text.lower(),
        "live_receipt_valid": valid.get("overall_integrity_valid") is True,
        "tampered_receipt_invalid": tampered.get("overall_integrity_valid") is False,
        "production_data_unmodified": tampered.get("production_data_modified") is False,
    }
    consistency = {
        "source": "LIVE_DEPLOYED_STAGE11_ENDPOINT",
        "pact": data.get("liveBackend", {}).get("pactId"),
        "backend_lifecycle": data.get("liveBackend", {}).get("currentLifecycle"),
        "checks": checks,
        "result": "PASS" if all(checks.values()) else "BLOCKED",
    }
    write("live-protected-case.json", data)
    write("ui-backend-consistency.json", consistency)
    write("receipt-verification.json", {
        "source": "LIVE_FIRESTORE_INTEGRITY_BUNDLE",
        "valid": valid,
        "tampered": tampered,
        "result": "PASS" if checks["live_receipt_valid"] and checks["tampered_receipt_invalid"] else "BLOCKED",
    })
    print(json.dumps(consistency, indent=2))
    return 0 if consistency["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
