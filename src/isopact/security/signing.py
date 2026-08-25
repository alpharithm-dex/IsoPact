from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from typing import Any, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed

from isopact.evidence.canonical import canonical_json_bytes
from isopact.observability import telemetry
from time import perf_counter


SIGNATURE_ALGORITHM = "EC_SIGN_P256_SHA256"


class SigningUnavailable(RuntimeError):
    pass


class DocumentSigner(Protocol):
    key_resource: str
    key_version: str
    algorithm: str
    def sign(self, data: bytes) -> bytes: ...
    def public_key_pem(self) -> str: ...


@dataclass(slots=True)
class KmsDocumentSigner:
    key_version: str
    client: Any
    algorithm: str = SIGNATURE_ALGORITHM

    @property
    def key_resource(self) -> str:
        return self.key_version.rsplit("/cryptoKeyVersions/", 1)[0]

    def sign(self, data: bytes) -> bytes:
        digest = hashlib.sha256(data).digest()
        started = perf_counter()
        try:
            response = self.client.asymmetric_sign(request={"name": self.key_version, "digest": {"sha256": digest}})
        except Exception as exc:
            raise SigningUnavailable(f"KMS_SIGNING_FAILED:{type(exc).__name__}") from exc
        telemetry.observe("isopact.kms.sign.duration", (perf_counter() - started) * 1000, tool_category="kms")
        return bytes(response.signature)

    def public_key_pem(self) -> str:
        return str(self.client.get_public_key(request={"name": self.key_version}).pem)


def signing_body(document: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in document.items() if key not in {"signature", "issuance_status"}}


def sign_document(body: dict[str, Any], signer: DocumentSigner) -> dict[str, Any]:
    signed_body = {
        **body,
        "signing_key_resource": signer.key_resource,
        "signing_key_version": signer.key_version,
        "signature_algorithm": signer.algorithm,
    }
    signature = signer.sign(canonical_json_bytes(signed_body))
    return {
        **signed_body,
        "signature": base64.b64encode(signature).decode("ascii"),
        "issuance_status": "SIGNED",
    }


def verify_signed_document(document: dict[str, Any], public_key_pem: str) -> tuple[bool, str | None]:
    with telemetry.span("isopact.receipt.verify", **{"isopact.receipt.id": document.get("receipt_id") or document.get("checkpoint_id")}):
        return _verify_signed_document(document, public_key_pem)


def _verify_signed_document(document: dict[str, Any], public_key_pem: str) -> tuple[bool, str | None]:
    if document.get("issuance_status") != "SIGNED" or not document.get("signature"):
        return False, "DOCUMENT_NOT_SIGNED"
    if document.get("signature_algorithm") != SIGNATURE_ALGORITHM:
        return False, "UNSUPPORTED_SIGNATURE_ALGORITHM"
    try:
        public_key = serialization.load_pem_public_key(public_key_pem.encode("ascii"))
        if not isinstance(public_key, ec.EllipticCurvePublicKey):
            return False, "PUBLIC_KEY_TYPE_MISMATCH"
        signature = base64.b64decode(document["signature"], validate=True)
        digest = hashlib.sha256(canonical_json_bytes(signing_body(document))).digest()
        public_key.verify(signature, digest, ec.ECDSA(Prehashed(hashes.SHA256())))
        return True, None
    except (InvalidSignature, ValueError, TypeError):
        return False, "SIGNATURE_INVALID"


def unsigned_pending_document(body: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        **body,
        "signature": None,
        "issuance_status": "SETTLED_RECEIPT_PENDING",
        "issuance_failure_reason": reason,
    }
