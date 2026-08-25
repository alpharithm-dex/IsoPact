from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import google.auth
from google.auth import impersonated_credentials
from google.cloud import kms_v1

from isopact.security.signing import KmsDocumentSigner, sign_document, signing_body, verify_signed_document


SCOPE = "https://www.googleapis.com/auth/cloud-platform"
OUT = ROOT / "artifacts" / "security"


def metric(values: list[float]) -> dict:
    ordered = sorted(values)
    return {
        "samples": len(values),
        "p50_ms": round(statistics.median(values), 3),
        "p95_ms": round(ordered[max(0, int(len(values) * .95 + .999999) - 1)], 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--signer-service-account", required=True)
    parser.add_argument("--key-version", required=True)
    args = parser.parse_args()
    checkpoint = json.loads((OUT / "live-kms-checkpoint.json").read_text())
    receipt = json.loads((OUT / "final-settlement-receipt.json").read_text())
    keys = json.loads((OUT / "public-keys.json").read_text())
    concurrency = json.loads((OUT / "claim-chain-concurrency.json").read_text())
    armor = json.loads((OUT / "model-armor-proof.json").read_text())
    source, _ = google.auth.default(scopes=[SCOPE])
    delegated = impersonated_credentials.Credentials(
        source_credentials=source, target_principal=args.signer_service_account,
        target_scopes=[SCOPE], lifetime=900,
    )
    signer = KmsDocumentSigner(args.key_version, kms_v1.KeyManagementServiceClient(credentials=delegated))
    checkpoint_times, receipt_times = [], []
    for _ in range(5):
        started = time.perf_counter_ns()
        sign_document(signing_body(checkpoint), signer)
        checkpoint_times.append((time.perf_counter_ns() - started) / 1_000_000)
    for _ in range(5):
        started = time.perf_counter_ns()
        sign_document(signing_body(receipt), signer)
        receipt_times.append((time.perf_counter_ns() - started) / 1_000_000)
    verification_times = []
    for _ in range(200):
        started = time.perf_counter_ns()
        valid, _ = verify_signed_document(receipt, keys[str(receipt["signing_key_version"])])
        if not valid:
            raise RuntimeError("known-valid receipt failed performance verification")
        verification_times.append((time.perf_counter_ns() - started) / 1_000_000)
    proof = {
        "claim_hashing": concurrency["performance_ms"]["claim_hashing"],
        "firestore_claim_append": concurrency["performance_ms"]["firestore_claim_append"],
        "kms_checkpoint_signing": metric(checkpoint_times),
        "kms_receipt_signing": metric(receipt_times),
        "local_public_key_verification": metric(verification_times),
        "model_armor_screening": armor["performance"],
        "environment": "proof measurements only; 25-way live Firestore claim append, live Cloud KMS and Model Armor, local public-key verification; no production throughput claim",
    }
    (OUT / "performance.json").write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(proof, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
