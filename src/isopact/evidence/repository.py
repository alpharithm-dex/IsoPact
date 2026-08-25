from __future__ import annotations

from typing import Any, Protocol

from isopact.gateway.activation import ActiveOutcomePact

from .models import (
    Evidence,
    EvidenceDelivery,
    IngestionResult,
    PactGraphSnapshot,
    Participant,
    StateClaim,
)


class PactGraphRepository(Protocol):
    def activate_graph(self, active_pact: ActiveOutcomePact, now: str) -> None: ...
    def add_participant(self, participant: Participant) -> None: ...
    def append_claim(self, claim: StateClaim) -> bool: ...
    def ingest_evidence(
        self, evidence: Evidence, delivery: EvidenceDelivery
    ) -> IngestionResult: ...
    def snapshot(self, pact_id: str) -> PactGraphSnapshot: ...
    def cleanup_pact(self, pact_id: str) -> None: ...
    def claims_for_pact(self, pact_id: str) -> list[dict[str, Any]]: ...
