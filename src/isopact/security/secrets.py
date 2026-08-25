from __future__ import annotations

from dataclasses import dataclass


SECRET_FIELDS = frozenset({
    "api_key", "access_token", "refresh_token", "client_secret", "password",
    "private_key", "webhook_secret", "authorization_header",
})
CONFIG_FIELDS = frozenset({
    "project_id", "project_number", "region", "service_url", "kms_key_resource",
    "kms_key_version", "model_armor_template", "public_key",
})


def classify_setting(name: str) -> str:
    lowered = name.strip().lower()
    if lowered in SECRET_FIELDS or any(token in lowered for token in ("password", "private_key", "client_secret", "webhook_secret")):
        return "SECRET"
    if lowered in CONFIG_FIELDS:
        return "CONFIGURATION"
    return "REVIEW_REQUIRED"


@dataclass(slots=True)
class SecretManagerValue:
    version_name: str
    client: object

    def access(self) -> str:
        response = self.client.access_secret_version(request={"name": self.version_name})
        return response.payload.data.decode("utf-8")
