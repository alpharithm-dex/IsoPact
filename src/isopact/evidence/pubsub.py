from __future__ import annotations

import json
from datetime import UTC
from typing import Any

from .models import EvidenceDelivery
from .pipeline import EvidencePipeline, utc_now
from isopact.observability import telemetry


def process_received_message(pipeline: EvidencePipeline, received: Any):
    message = received.message
    payload = json.loads(message.data.decode("utf-8"))
    publish_time = message.publish_time
    publish_timestamp = publish_time.astimezone(UTC).isoformat() if publish_time else None
    delivery = EvidenceDelivery(
        delivery_id=f"pubsub_{message.message_id}",
        delivery_mechanism="GOOGLE_CLOUD_PUBSUB",
        pubsub_message_id=message.message_id,
        publish_timestamp=publish_timestamp,
        received_at=utc_now(),
        attributes=dict(message.attributes),
    )
    source_link = telemetry.causal_link(
        dict(message.attributes),
        **{
            "isopact.pact_id": str(payload.get("pact_id", "")),
            "isopact.source_event_id": str(payload.get("source_event_id", "")),
        },
    )
    links = (source_link,) if source_link is not None else ()
    return pipeline.ingest_event(payload, delivery, causal_links=links)
