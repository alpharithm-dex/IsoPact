# ADR-025: KMS signing and key rotation

Status: Accepted

Use a dedicated Cloud KMS asymmetric EC P-256 SHA-256 key in `africa-south1`. A dedicated signer identity alone receives key-level signing authority. Store key resource, exact version, algorithm and signature in every checkpoint and receipt; retain public keys for offline verification.

New versions sign new artifacts while old artifacts verify with their recorded versions. The private key is non-exportable and never generated locally for production proof. Signing failure changes receipt issuance to pending/failed, not business settlement truth.
