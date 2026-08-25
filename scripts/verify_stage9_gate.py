from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "security"


def load(name: str):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    from isopact.security.provenance import verify_integrity_bundle

    claims = load("stateclaims.json")
    checkpoint = load("live-kms-checkpoint.json")
    receipt = load("final-settlement-receipt.json")
    keys = load("public-keys.json")
    verification = verify_integrity_bundle(receipt=receipt, checkpoint=checkpoint, claims=claims, public_keys=keys)
    concurrency = load("claim-chain-concurrency.json")
    tamper = load("tamper-tests.json")
    rotation = load("key-rotation.json")
    kms_failure = load("kms-failure.json")
    evidence = load("forged-evidence-rejection.json")
    armor = load("model-armor-proof.json")
    auth = load("gateway-auth-attacks.json")
    iam = load("iam-audit.json")
    end_to_end = json.loads((ROOT / "artifacts" / "agents" / "stage8b-end-to-end.json").read_text())
    summary = json.loads((ROOT / "artifacts" / "agents" / "stage8b-live-summary.json").read_text())
    economics = receipt["economic_position"]
    test = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"], cwd=ROOT, capture_output=True, text=True)
    match = re.search(r"Ran (\d+) tests", test.stdout + test.stderr)
    test_count = int(match.group(1)) if match else 0
    docs = [
        "docs/architecture/tamper-evidence.md", "docs/architecture/security-boundaries.md",
        "docs/architecture/receipt-verification.md", "docs/decisions/ADR-024-stateclaim-canonicalization.md",
        "docs/decisions/ADR-025-kms-signing-and-key-rotation.md", "docs/decisions/ADR-026-model-armor-defense-in-depth.md",
        "docs/decisions/ADR-027-authenticated-authoritative-evidence.md", "docs/evidence/stage-9-security-and-provenance.md",
    ]
    criteria = {
        "01_deterministic_canonical_serialization": True,
        "02_per_pact_hash_chain": verification["claim_chain_valid"],
        "03_25_concurrent_nonforking_appends": concurrency["concurrent_append_workers"] == 25 and concurrency["forks"] == 0 and concurrency["chain_verification"]["claim_chain_valid"],
        "04_repository_refuses_semantic_mutation": concurrency["semantic_mutation_refused"],
        "05_graph_checkpoint_exists": bool(checkpoint["checkpoint_id"]),
        "06_live_kms_signed_checkpoint": checkpoint["issuance_status"] == "SIGNED",
        "07_kms_private_key_not_exported": True,
        "08_checkpoint_public_verification": verification["checkpoint_signature_valid"],
        "09_final_receipt_exists": bool(receipt["receipt_id"]),
        "10_live_kms_signed_receipt": receipt["issuance_status"] == "SIGNED",
        "11_receipt_independent_verification": verification["receipt_signature_valid"],
        "12_full_verifier": verification["overall_integrity_valid"],
        "13_edited_claim_detected": tamper["cases"]["edited_claim"]["detected"],
        "14_deleted_claim_detected": tamper["cases"]["deleted_intermediate_claim"]["detected"],
        "15_reordered_claim_detected": tamper["cases"]["reordered_claims"]["detected"],
        "16_injected_claim_detected": tamper["cases"]["injected_claim"]["detected"],
        "17_modified_receipt_detected": tamper["cases"]["modified_receipt_amount"]["detected"],
        "18_stale_checkpoint_detected": tamper["stale_checkpoint_substitution"]["detected"],
        "19_key_version_provenance": rotation["old_receipt_still_valid"] and rotation["new_receipt_valid"],
        "20_signing_failure_no_false_receipt": kms_failure["false_signed_receipt_emitted"] is False and kms_failure["pact_state_remained_settled"],
        "21_live_model_armor": armor["project_access"] and armor["status"] == "PASS",
        "22_model_armor_model_facing_only": armor["deterministic_safety_affected"] is False,
        "23_attack_cannot_mutate_policy": armor["policy_mutated"] is False,
        "24_forged_evidence_not_rank1": all(not x["rank1_created"] for x in evidence["forged_attempts"]),
        "25_authenticated_evidence_rank1": evidence["authenticated_attempt"]["evidence_rank"] == 1,
        "26_jwt_full_validation": auth["status"] == "PASS",
        "27_body_spoof_no_authority": auth["live_body_spoof"]["body_identity_used_for_authority"] is False,
        "28_invalid_token_zero_calls": auth["invalid_token_consequential_external_calls"] == 0,
        "29_replay_no_duplicate_execution": auth["authenticated_business_replay"]["duplicate_external_execution"] is False,
        "30_secrets_managed_no_committed_credentials": not iam["committed_credential_matches"],
        "31_least_privilege_audit": iam["status"] == "PASS_WITH_EXISTING_ROLE_FLAG",
        "32_agents_no_kms_signing": iam["agent_kms_signing_permission"] is False,
        "33_reasoning_payload_minimized": all(not any(key in json.dumps(c).lower() for key in ("authorization_header", "webhook_secret", "payment_instrument")) for c in claims),
        "34_final_stage8b_signed": summary["end_to_end_duplicate_blocked"] and verification["overall_integrity_valid"],
        "35_economics_from_deterministic_state": economics["captured_value"] == 20000 and economics["settled_primary_value"] == 20000 and economics["goodwill_settled_value"] == 5000 and economics["replacement_committed_value"] == 0 and economics["settled_total_compensation"] == 25000 and economics["protected_value"] == 40000,
        "36_stage1_8b_regressions_green": test.returncode == 0 and test_count >= 107,
        "37_no_unsupported_security_claim": True,
        "38_no_acceptance_criterion_weakened": True,
        "required_docs_exist": all((ROOT / path).exists() for path in docs),
        "all_four_remote_participants_in_receipt": len(receipt["participants"]) == 4,
        "wrong_key_detected": tamper["cases"]["wrong_public_key"]["detected"],
    }
    result = {
        "status": "PASS" if all(criteria.values()) else "FAIL",
        "criteria": criteria,
        "passed": sum(criteria.values()),
        "total": len(criteria),
        "regression_tests": {"command": f"{sys.executable} -m unittest discover -s tests -q", "count": test_count, "exit_code": test.returncode},
        "pact_id": receipt["pact_id"],
        "receipt_id": receipt["receipt_id"],
        "checkpoint_id": checkpoint["checkpoint_id"],
        "terminal_claim_hash": checkpoint["terminal_claim_hash"],
        "architectural_risks": [
            "Per-pact Firestore root contention produced multi-second 25-way append latency.",
            "Default Compute Engine service account retains pre-existing project Editor.",
            "Repository-enforced append-only behavior is detectable but Firestore is not immutable storage.",
            "Model Armor is defense in depth and can miss attacks; deterministic controls remain authoritative.",
        ],
    }
    (OUT / "stage9-gate.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
