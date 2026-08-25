from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["ISOPACT_STAGE11_FRONTEND"] = str(ROOT / "frontend" / "dist")
os.environ["ISOPACT_STAGE11_PUBLIC_KEYS"] = str(ROOT / "artifacts" / "security" / "public-keys.json")

from services.outcome_gateway.main import STAGE11_PACT_ID, _live_integrity, db

valid = _live_integrity("LIVE")
tampered = _live_integrity("TAMPERED_ARTIFACT")
claim_rows = [doc.to_dict() for doc in db.collection("pacts").document(STAGE11_PACT_ID).collection("claims").stream()]
sequences = sorted((item.get("sequence_number"), item.get("sequence"), item.get("claim_id"), item.get("previous_claim_hash"), item.get("claim_hash")) for item in claim_rows)
result = {"valid": valid, "tampered": tampered, "claim_sequences": sequences, "result": "PASS" if valid["overall_integrity_valid"] and not tampered["overall_integrity_valid"] else "BLOCKED"}
print(json.dumps(result, indent=2))
raise SystemExit(0 if result["result"] == "PASS" else 1)
