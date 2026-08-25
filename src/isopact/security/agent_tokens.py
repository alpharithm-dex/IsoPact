from __future__ import annotations

from typing import Any, Mapping

import jwt


def verify_agent_identity_token(
    token: str, *, jwks_client: Any, expected_issuer: str, expected_audience: str,
    subject_roles: Mapping[str, Any],
) -> tuple[Any, dict[str, Any]]:
    try:
        key = jwks_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key.key,
            algorithms=["RS256"],
            audience=expected_audience,
            issuer=expected_issuer,
            leeway=0,
            options={"require": ["exp", "iat", "iss", "sub", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise PermissionError("caller token verification failed") from exc
    subject = str(claims.get("sub", ""))
    if subject not in subject_roles:
        raise PermissionError("unmapped caller identity")
    return subject_roles[subject], {
        "verification": "GOOGLE_STS_JWKS_RS256",
        "token_subject": subject,
        "token_audience": claims.get("aud"),
        "token_issuer": claims.get("iss"),
        "token_expiration": claims.get("exp"),
        "token_not_before": claims.get("nbf"),
    }
