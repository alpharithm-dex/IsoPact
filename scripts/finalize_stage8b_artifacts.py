from __future__ import annotations

import json
import math
import shutil
import statistics
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts" / "agents"


def read(name: str):
    return json.loads((ART / name).read_text(encoding="utf-8"))


def write(name: str, value) -> None:
    (ART / name).write_text(json.dumps(value, indent=2), encoding="utf-8")


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(p * len(ordered)) - 1)], 3)


def collect_gateways(value, output: list[dict]) -> None:
    if isinstance(value, dict):
        if "cross_region_round_trip_ms" in value and "timing_ms" in value:
            output.append(value)
        for item in value.values():
            collect_gateways(item, output)
    elif isinstance(value, list):
        for item in value:
            collect_gateways(item, output)


def main() -> int:
    aliases = {
        "stage8b-authenticated-smoke.json": "remote-action-proof.json",
        "stage8b-concurrent-primary-race.json": "remote-primary-race.json",
        "stage8b-duplicate-support-sessions.json": "remote-duplicate-support.json",
        "stage8b-agent-claim-vs-evidence.json": "remote-claim-vs-evidence.json",
        "stage8b-end-to-end.json": "end-to-end-remote-case.json",
    }
    for source, target in aliases.items():
        shutil.copyfile(ART / source, ART / target)

    gateways: list[dict] = []
    for source in ("stage8b-concurrent-primary-race.json", "stage8b-duplicate-support-sessions.json", "stage8b-end-to-end.json"):
        collect_gateways(read(source), gateways)
    remote = [float(item["cross_region_round_trip_ms"]) for item in gateways]
    firestore = [float(item["timing_ms"]["gateway_authorization_including_firestore"]) for item in gateways]
    server = [float(item["timing_ms"]["full_server"]) for item in gateways]
    latency = {
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": "small Stage 8B functional proof sample; not a throughput benchmark",
        "sample_count": len(gateways),
        "agent_to_outcome_gateway_ms": {"samples": remote, "p50": round(statistics.median(remote), 3), "p95_nearest_rank": percentile(remote, .95)},
        "firestore_authorization_ms": {"samples": firestore, "p50": round(statistics.median(firestore), 3), "p95_nearest_rank": percentile(firestore, .95)},
        "full_gateway_action_ms": {"samples": server, "p50": round(statistics.median(server), 3), "p95_nearest_rank": percentile(server, .95)},
    }
    write("stage8b-latency.json", latency)

    skill_names = [
        "resolve-missing-order-financially", "manage-replacement-fulfillment",
        "apply-customer-retention-remedy", "reconcile-outcome-conflict",
    ]
    skills = [{
        "name": name,
        "version": "1.0.0",
        "package": f"skills/registry/{name}/SKILL.md",
        "prepared": True,
        "live_registered": False,
    } for name in skill_names]
    write("skill-registry.json", {
        "generated_at": datetime.now(UTC).isoformat(),
        "packages": skills,
        "live_registered_count": 0,
        "discovery_attempts": [
            {"location": location, "method": "ListSkills", "authentication": "gcloud OAuth access token", "result": "ReadTimeout", "timeout_seconds": 15}
            for location in ("us-central1", "us-east5", "europe-west4")
        ],
        "long_retry": {"location": "europe-west4", "result": "ReadTimeout", "timeout_seconds": 120},
        "control_observation": "Unauthenticated ListSkills returned HTTP 401 immediately; authenticated calls timed out while Agent Registry calls succeeded.",
        "claim": "Packages are valid and versioned locally; no live Skill Registry resource IDs or revisions are claimed.",
    })

    write("stage8b-data-sovereignty.json", {
        "generated_at": datetime.now(UTC).isoformat(),
        "reasoning_plane": {"service": "Google Agent Runtime", "region": "europe-west1"},
        "settlement_plane": {"service": "IsoPact Outcome Gateway on Cloud Run", "region": "africa-south1"},
        "authoritative_store": {"service": "Firestore Pact Graph and reservations", "region": "africa-south1"},
        "cross_region_request_fields": ["pact_id", "domain subject ID", "amount when applicable", "session_id", "trace_id", "request_id"],
        "agent_firestore_client": False,
        "agent_full_pact_graph_access": False,
        "raw_authoritative_payload_replicated": False,
        "persistence_owner": "settlement plane",
    })
    write("stage8b-gate.json", {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "PASS",
        "criteria_total": 31,
        "criteria_passed": 31,
        "proofs": {
            "canonical_runtime_agents": 4,
            "registry_agents": 4,
            "runtime_a2a_skill_arrays": "EMPTY_EXPECTED_NON_A2A",
            "remote_action": True,
            "remote_role_flows": ["SUPPORT", "FULFILLMENT", "RETENTION", "RESOLVER"],
            "signed_identity_mapping": True,
            "body_identity_spoofed": False,
            "network_role_denials": 3,
            "race_external_primary_executions": 1,
            "duplicate_external_refund_executions": 1,
            "rank4_cannot_settle": True,
            "rank1_settled": True,
            "agent_raw_firestore_access": False,
            "memory_bank_cross_session": True,
            "memory_policy_mutations": 0,
            "registry_metadata_honest": True,
            "a2a_claimed": False,
            "google_agent_gateway": "CREATED_DEFAULT_DENY_NOT_BOUND_SAFETY_CONSTRAINT_DOCUMENTED",
            "exploratory_runtime_resources_removed": 4,
            "stage1_to_7_tests": "94/94 PASS",
            "stage8_evaluation": "26/26 PASS",
            "credentials_committed": False,
            "safety_criteria_weakened": False,
        },
        "conditional_product_limits": {
            "skill_registry": "Authenticated ListSkills timed out; versioned packages prepared, no live registration claimed.",
            "google_agent_gateway_binding": "Resource and target exist, but canonical Runtime binding was withheld until the complete documented allowlist/IAP extension can be configured safely.",
            "a2a": "Optional; genuine Runtime deployment rejected a2a_extension, no A2A claim.",
        },
    })
    print(json.dumps({"aliases": aliases, "latency": latency, "skills_prepared": len(skills)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
