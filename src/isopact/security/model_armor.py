from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


class ScreeningUnavailable(RuntimeError):
    pass


class ScreeningBlocked(ValueError):
    pass


@dataclass(slots=True)
class ModelArmorScreener:
    template_name: str
    client: Any
    firestore_client: Any | None = None

    def screen_untrusted_text(self, text: str, *, boundary: str, pact_id: str | None = None) -> dict[str, Any]:
        from google.cloud import modelarmor_v1

        started = time.perf_counter()
        operation_id = "screen_" + hashlib.sha256(
            f"{self.template_name}:{boundary}:{text}".encode("utf-8")
        ).hexdigest()[:24]
        try:
            response = self.client.sanitize_user_prompt(request={
                "name": self.template_name,
                "user_prompt_data": modelarmor_v1.DataItem(text=text),
            })
        except Exception as exc:
            raise ScreeningUnavailable(f"MODEL_ARMOR_UNAVAILABLE:{type(exc).__name__}") from exc
        raw = modelarmor_v1.SanitizeUserPromptResponse.to_dict(response)
        match_state = raw.get("sanitization_result", {}).get("filter_match_state", 0)
        match_found = match_state in {2, "MATCH_FOUND", "FILTER_MATCH_STATE_MATCH_FOUND"}
        metadata = {
            "screening_operation_id": operation_id,
            "template": self.template_name,
            "boundary": boundary,
            "pact_id": pact_id,
            "input_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "input_persisted": False,
            "filter_match_state": match_state,
            "outcome": "BLOCK" if match_found else "ALLOW",
            "screened_at": datetime.now(UTC).isoformat(),
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "detection_categories": sorted(raw.get("sanitization_result", {}).get("filter_results", {}).keys()) if isinstance(raw.get("sanitization_result", {}).get("filter_results"), dict) else [],
        }
        if self.firestore_client is not None:
            self.firestore_client.collection("security_screenings").document(operation_id).create(metadata)
        if metadata["outcome"] == "BLOCK":
            raise ScreeningBlocked("MODEL_ARMOR_BLOCKED_UNTRUSTED_INPUT")
        return metadata
