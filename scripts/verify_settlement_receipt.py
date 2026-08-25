from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from isopact.security.provenance import verify_integrity_bundle
from isopact.security.signing import verify_signed_document


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Independently verify an IsoPact Settlement Receipt.")
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--claims", type=Path)
    parser.add_argument("--public-keys", type=Path)
    parser.add_argument("--signature-only", action="store_true")
    args = parser.parse_args()
    directory = args.receipt.resolve().parent
    receipt = load(args.receipt)
    public_keys = load(args.public_keys or directory / "public-keys.json")
    if args.signature_only:
        valid, reason = verify_signed_document(receipt, public_keys.get(receipt.get("signing_key_version"), ""))
        result = {
            "receipt_signature_valid": valid,
            "overall_integrity_valid": valid,
            "reason_codes": [] if valid else [reason or "SIGNATURE_INVALID"],
            "scope": "RECEIPT_SIGNATURE_ONLY",
        }
    else:
        checkpoint = load(args.checkpoint or directory / "live-kms-checkpoint.json")
        claims = load(args.claims or directory / "stateclaims.json")
        result = verify_integrity_bundle(
            receipt=receipt, checkpoint=checkpoint, claims=claims, public_keys=public_keys,
        )
        result["scope"] = "FULL_INTEGRITY"
        result["external_source_truth_queried"] = False
        result["meaning"] = "Integrity/provenance verified; source truth remains the authenticated adapter's responsibility."
    print(json.dumps(result, indent=2))
    print(f"OVERALL INTEGRITY: {'VALID' if result['overall_integrity_valid'] else 'INVALID'}")
    return 0 if result["overall_integrity_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
