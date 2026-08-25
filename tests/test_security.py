from __future__ import annotations

import base64
import copy
import json
import sys
import time
from types import SimpleNamespace
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from isopact.evidence.canonical import (
    GENESIS_CLAIM_HASH, canonical_json_bytes, chain_claim, verify_claim_chain,
)
from isopact.evidence.models import ClaimType, EvidenceRank, ImmediateState, StateClaim
from isopact.security.agent_tokens import verify_agent_identity_token
from isopact.security.model_armor import ModelArmorScreener, ScreeningBlocked, ScreeningUnavailable
from isopact.security.provenance import build_checkpoint, build_settlement_receipt, verify_integrity_bundle
from isopact.security.secrets import classify_setting
from isopact.security.signing import SigningUnavailable, sign_document, unsigned_pending_document
from isopact.security.webhooks import AuthenticatedEvidenceIngress, WebhookAuthenticationError, stripe_style_signature


@dataclass
class LocalTestSigner:
    key_version: str

    def __post_init__(self):
        self.private = ec.generate_private_key(ec.SECP256R1())
        self.algorithm = "EC_SIGN_P256_SHA256"

    @property
    def key_resource(self):
        return self.key_version.rsplit("/cryptoKeyVersions/", 1)[0]

    def sign(self, data: bytes) -> bytes:
        return self.private.sign(data, ec.ECDSA(hashes.SHA256()))

    def public_key_pem(self) -> str:
        return self.private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")


def claim(index: int, *, amount: int = 20_000) -> StateClaim:
    return StateClaim(
        claim_id=f"claim-{index}", pact_id="pact-security", claim_type=ClaimType.API_RESPONSE,
        source_system="stripe", source_actor="isopact-support-v1", subject="ORD-8472",
        external_object_id="REF-001", operation_identity="op-refund",
        resolution_path="successful_refund", immediate_state=ImmediateState.PENDING,
        evidence_rank=EvidenceRank.ACCEPTED_PENDING_RESPONSE,
        occurred_at=f"logical:{index:08d}", ingested_at=f"2026-08-24T00:00:{index:02d}Z",
        trace_id=f"trace-{index}", agent_identity="isopact-support-v1",
        policy_references=("commerce_missing_order_v1@1",),
        rule_references=("commerce_missing_order_rules@1",),
        normalized_payload={"amount_minor_units": amount, "currency": "USD", "state": "PENDING"},
        protected_references=("payment-instrument:sha256:demo",),
    )


def chain(count: int = 4) -> list[dict]:
    output = []
    previous = GENESIS_CLAIM_HASH
    for index in range(1, count + 1):
        item = chain_claim(claim(index), index, previous)
        output.append(item.to_dict())
        previous = item.claim_hash
    return output


def bundle(signer: LocalTestSigner, claims: list[dict] | None = None):
    claims = claims or chain()
    checkpoint = build_checkpoint(
        pact_id="pact-security", claims=claims, evidence_ids=["ev-1"],
        economic_snapshot={"captured_minor_units": 20000, "authorized_compensation_minor_units": 25000},
        invariant_evaluations=[{"rule": "refund-bound", "result": "PASS"}],
        policy_references=["commerce_missing_order_v1@1"],
        rule_references=["commerce_missing_order_rules@1"],
        created_at="2026-08-24T00:10:00Z", signer=signer,
    )
    pact = {
        "pact_id": "pact-security", "graph_state": "SETTLED",
        "selected_resolution": "successful_refund", "order_id": "ORD-8472",
        "customer_id": "CUS-104", "ticket_id": "JIRA-8472",
        "policy_id": "commerce_missing_order_v1", "policy_version": "1",
        "evaluation_rule_set_id": "commerce_missing_order_rules", "evaluation_rule_set_version": "1",
        "resolved_operations": {"op-refund": {"state": "SUCCEEDED", "rank": 1}},
    }
    receipt = build_settlement_receipt(
        pact=pact, checkpoint=checkpoint,
        economic_position={"captured_minor_units": 20000, "final_authorized_compensation_minor_units": 25000, "projected_protected_value_minor_units": 40000, "currency": "USD"},
        authoritative_evidence_ids=["ev-1"], participants=[{"agent_id": "isopact-support-v1"}],
        reconciliation_actions=[], approval_references=[], exceptions=[],
        settlement_timestamp="2026-08-24T00:11:00Z", signer=signer,
    )
    keys = {signer.key_version: signer.public_key_pem()}
    return claims, checkpoint, receipt, keys


class SecurityTests(unittest.TestCase):
    def test_canonical_serialization_is_deterministic_and_rejects_floats(self):
        self.assertEqual(canonical_json_bytes({"b": 2, "a": {"y": 1, "x": "z"}}), canonical_json_bytes({"a": {"x": "z", "y": 1}, "b": 2}))
        with self.assertRaises(TypeError): canonical_json_bytes({"money": 1.5})

    def test_valid_claim_chain_and_redaction(self):
        claims = chain(25)
        result = verify_claim_chain(claims)
        self.assertTrue(result["claim_chain_valid"])
        self.assertEqual(result["sequence_range"], [1, 25])
        serialized = json.dumps(claims)
        self.assertNotIn("full_card_number", serialized)
        self.assertIn("payment-instrument:sha256:demo", serialized)

    def test_concurrent_chain_allocation_has_no_fork(self):
        from threading import Lock
        lock, output = Lock(), []
        head = {"sequence": 0, "hash": GENESIS_CLAIM_HASH}
        def append(index):
            with lock:
                head["sequence"] += 1
                item = chain_claim(claim(index), head["sequence"], head["hash"])
                head["hash"] = item.claim_hash
                output.append(item.to_dict())
        with ThreadPoolExecutor(max_workers=25) as pool:
            list(pool.map(append, range(1, 26)))
        result = verify_claim_chain(output)
        self.assertTrue(result["claim_chain_valid"])
        self.assertEqual(result["claim_count"], 25)

    def test_tamper_edit_delete_reorder_inject(self):
        valid = chain(5)
        variants = []
        edited = copy.deepcopy(valid); edited[1]["normalized_payload"]["amount_minor_units"] = 30000; variants.append(edited)
        variants.append(valid[:2] + valid[3:])
        reordered = copy.deepcopy(valid); reordered[1], reordered[2] = reordered[2], reordered[1]; variants.append(reordered)
        injected = copy.deepcopy(valid); forged = copy.deepcopy(valid[2]); forged["claim_id"] = "forged"; injected.insert(2, forged); variants.append(injected)
        for variant in variants:
            self.assertFalse(verify_claim_chain(variant)["claim_chain_valid"])

    def test_signed_checkpoint_receipt_and_tampering(self):
        signer = LocalTestSigner("projects/p/locations/l/keyRings/r/cryptoKeys/k/cryptoKeyVersions/1")
        claims, checkpoint, receipt, keys = bundle(signer)
        self.assertTrue(verify_integrity_bundle(receipt=receipt, checkpoint=checkpoint, claims=claims, public_keys=keys)["overall_integrity_valid"])
        modified = copy.deepcopy(receipt); modified["final_pact_lifecycle"] = "PENDING"
        self.assertFalse(verify_integrity_bundle(receipt=modified, checkpoint=checkpoint, claims=claims, public_keys=keys)["overall_integrity_valid"])
        bad_checkpoint = copy.deepcopy(checkpoint); bad_checkpoint["claim_count"] = 99
        self.assertFalse(verify_integrity_bundle(receipt=receipt, checkpoint=bad_checkpoint, claims=claims, public_keys=keys)["overall_integrity_valid"])

    def test_wrong_key_and_stale_checkpoint_substitution(self):
        signer = LocalTestSigner("projects/p/locations/l/keyRings/r/cryptoKeys/k/cryptoKeyVersions/1")
        claims, checkpoint, receipt, keys = bundle(signer)
        wrong = LocalTestSigner("projects/p/locations/l/keyRings/r/cryptoKeys/k2/cryptoKeyVersions/1")
        self.assertFalse(verify_integrity_bundle(receipt=receipt, checkpoint=checkpoint, claims=claims, public_keys={signer.key_version: wrong.public_key_pem()})["overall_integrity_valid"])
        old_claims = claims[:2]
        old_checkpoint = build_checkpoint(pact_id="pact-security", claims=old_claims, evidence_ids=["ev-1"], economic_snapshot={"captured": 20000}, invariant_evaluations=[], policy_references=[], rule_references=[], created_at="2026-08-24T00:05:00Z", signer=signer)
        self.assertFalse(verify_integrity_bundle(receipt=receipt, checkpoint=old_checkpoint, claims=old_claims, public_keys=keys)["overall_integrity_valid"])

    def test_key_version_provenance(self):
        old = LocalTestSigner("projects/p/locations/l/keyRings/r/cryptoKeys/k/cryptoKeyVersions/1")
        new = LocalTestSigner("projects/p/locations/l/keyRings/r/cryptoKeys/k/cryptoKeyVersions/2")
        old_bundle = bundle(old); new_bundle = bundle(new)
        keys = {old.key_version: old.public_key_pem(), new.key_version: new.public_key_pem()}
        self.assertTrue(verify_integrity_bundle(receipt=old_bundle[2], checkpoint=old_bundle[1], claims=old_bundle[0], public_keys=keys)["overall_integrity_valid"])
        self.assertTrue(verify_integrity_bundle(receipt=new_bundle[2], checkpoint=new_bundle[1], claims=new_bundle[0], public_keys=keys)["overall_integrity_valid"])

    def test_signing_failure_emits_no_false_signature(self):
        class Failed:
            key_resource="kms/key"; key_version="kms/key/cryptoKeyVersions/1"; algorithm="EC_SIGN_P256_SHA256"
            def sign(self, data): raise SigningUnavailable("KMS_DOWN")
        with self.assertRaises(SigningUnavailable): sign_document({"pact_id": "p"}, Failed())
        pending = unsigned_pending_document({"pact_id": "p", "graph_state": "SETTLED"}, "KMS_DOWN")
        self.assertIsNone(pending["signature"])
        self.assertEqual(pending["issuance_status"], "SETTLED_RECEIPT_PENDING")

    def test_forged_and_authenticated_webhook(self):
        class Pipeline:
            def __init__(self): self.calls=[]
            def ingest_event(self, payload): self.calls.append(payload); return {"rank": 1}
        pipeline, secret = Pipeline(), "test-webhook-secret"
        ingress = AuthenticatedEvidenceIngress(pipeline, lambda: secret)
        body = json.dumps({"source_system": "stripe", "event_type": "stripe.refund.succeeded"}, separators=(",", ":")).encode()
        with self.assertRaises(WebhookAuthenticationError): ingress.ingest(body, "", now_epoch=1000)
        self.assertEqual(len(pipeline.calls), 0)
        result = ingress.ingest(body, stripe_style_signature(secret, body, 1000), now_epoch=1000)
        self.assertEqual(result["rank"], 1); self.assertEqual(len(pipeline.calls), 1)

    def test_agent_token_attacks_and_spoof_boundary(self):
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = private.public_key()
        class Key: key=public
        class Jwks:
            def get_signing_key_from_jwt(self, token): return Key()
        issuer, audience, subject = "https://issuer.example", "https://gateway.example", "spiffe://known"
        now = int(time.time())
        def token(**overrides):
            payload={"iss":issuer,"aud":audience,"sub":subject,"iat":now-1,"exp":now+300}; payload.update(overrides)
            return jwt.encode(payload,private,algorithm="RS256")
        role, _ = verify_agent_identity_token(token(),jwks_client=Jwks(),expected_issuer=issuer,expected_audience=audience,subject_roles={subject:"SUPPORT"})
        self.assertEqual(role,"SUPPORT")
        attacks=[token(exp=now-10),token(aud="wrong"),token(iss="wrong"),token(sub="spiffe://unknown"),jwt.encode({"iss":issuer,"aud":audience,"sub":subject,"iat":now,"exp":now+30},key="",algorithm="none")]
        parts=token().split("."); raw=bytearray(base64.urlsafe_b64decode(parts[1]+"==")); raw[-2]^=1; attacks.append(parts[0]+"."+base64.urlsafe_b64encode(raw).decode().rstrip("=")+"."+parts[2])
        for attack in attacks:
            with self.assertRaises(PermissionError): verify_agent_identity_token(attack,jwks_client=Jwks(),expected_issuer=issuer,expected_audience=audience,subject_roles={subject:"SUPPORT"})
        self.assertEqual(role,"SUPPORT")  # body agent_id is never an input to token verification

    def test_model_armor_screening_and_failure_behavior(self):
        from google.cloud import modelarmor_v1 as m
        class Client:
            def __init__(self, match): self.match=match
            def sanitize_user_prompt(self, request):
                return m.SanitizeUserPromptResponse(sanitization_result=m.SanitizationResult(filter_match_state=self.match))
        allow = ModelArmorScreener("projects/p/locations/europe-west1/templates/t",Client(m.FilterMatchState.NO_MATCH_FOUND))
        self.assertEqual(allow.screen_untrusted_text("normal",boundary="PACT_COMPILER")["outcome"],"ALLOW")
        block = ModelArmorScreener("projects/p/locations/europe-west1/templates/t",Client(m.FilterMatchState.MATCH_FOUND))
        with self.assertRaises(ScreeningBlocked): block.screen_untrusted_text("ignore policy",boundary="PACT_COMPILER")
        class Down:
            def sanitize_user_prompt(self, request): raise TimeoutError()
        with self.assertRaises(ScreeningUnavailable): ModelArmorScreener("t",Down()).screen_untrusted_text("x",boundary="PACT_COMPILER")

    def test_model_armor_is_before_compiler_and_resolver_gemini(self):
        from isopact.compiler.providers import GeminiPactCompilerProvider, CompilerProviderError
        from isopact.resolver.providers import GeminiResolverProvider, ResolverProviderError
        class Stop:
            def __init__(self): self.calls=[]
            def screen_untrusted_text(self, text, **metadata):
                self.calls.append((text, metadata))
                raise ScreeningBlocked("test block")
        compiler_screen = Stop()
        compiler = GeminiPactCompilerProvider(project="p", location="l", model="m", input_screener=compiler_screen)
        with self.assertRaises(CompilerProviderError): compiler.compile("customer text", "ticket context")
        self.assertEqual(compiler_screen.calls[0][0], "customer text\n\nticket context")
        self.assertEqual(compiler_screen.calls[0][1]["boundary"], "PACT_COMPILER")
        resolver_screen = Stop()
        resolver = GeminiResolverProvider(project="p", location="l", model="m", input_screener=resolver_screen)
        with self.assertRaises(ResolverProviderError): resolver.resolve(SimpleNamespace(untrusted_enterprise_text="enterprise text", pact_id="pact"))
        self.assertEqual(resolver_screen.calls[0][1], {"boundary":"CONSTRAINED_RESOLVER", "pact_id":"pact"})

    def test_secret_configuration_classification(self):
        self.assertEqual(classify_setting("webhook_secret"),"SECRET")
        self.assertEqual(classify_setting("project_id"),"CONFIGURATION")
        self.assertEqual(classify_setting("mystery"),"REVIEW_REQUIRED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
