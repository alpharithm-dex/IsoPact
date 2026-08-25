from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "observability"
PATTERNS = {
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "authorization": re.compile(r"authorization.{0,20}bearer", re.I),
    "webhook_secret": re.compile(r"whsec_[A-Za-z0-9]+"),
    "private_key": re.compile(r"BEGIN (?:RSA |EC )?PRIVATE KEY"),
    "payment_secret": re.compile(r"(?:sk_live_|card_number|payment_instrument)", re.I),
    "privacy_canary": re.compile(r"ISOPACT_TRACE_PRIVACY_CANARY"),
    "raw_model_payload": re.compile(r"gcp\.vertex\.agent\.(?:llm_request|llm_response)"),
}


def main() -> int:
    matches = {name: [] for name in PATTERNS}
    for path in OUT.glob("*.json"):
        if path.name in {"privacy-canary.json", "privacy-audit.json"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for name, pattern in PATTERNS.items():
            if pattern.search(text):
                matches[name].append(path.name)
    result = {"scope": "sanitized Stage 10 observability JSON artifacts", "matches": matches,
              "prohibited_match_count": sum(len(items) for items in matches.values()),
              "result": "PASS" if not any(matches.values()) else "FAIL"}
    (OUT / "privacy-audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
