from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

from .models import EconomicEvent, EconomicPhase


@dataclass(frozen=True, slots=True)
class EconomicPosition:
    as_of: int
    currency: str
    original_minor_units: int
    settled_minor_units: int
    pending_minor_units: int
    projected_only_minor_units: int
    projected_total_minor_units: int
    projected_excess_minor_units: int
    authorized_exception_minor_units: int
    provenance: tuple[dict[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["provenance"] = list(self.provenance)
        return result


class EconomicLedger:
    def __init__(self) -> None:
        self.events: list[EconomicEvent] = []
        self._sequence = 0

    def append(self, **values: object) -> EconomicEvent:
        self._sequence += 1
        event = EconomicEvent(event_id=f"ECO-{self._sequence:04d}", **values)  # type: ignore[arg-type]
        self.events.append(event)
        return event

    def position(
        self, *, as_of: int, original_minor_units: int, currency: str
    ) -> EconomicPosition:
        latest: dict[str, EconomicEvent] = {}
        for event in self.events:
            if event.logical_timestamp <= as_of:
                latest[event.external_object_id] = event

        settled = pending = projected_only = authorized_exception = 0
        provenance: list[dict[str, object]] = []
        for object_id in sorted(latest):
            event = latest[object_id]
            value = event.amount_minor_units or 0
            if event.phase in {EconomicPhase.FAILED, EconomicPhase.REVERSED}:
                contribution = 0
            elif event.phase is EconomicPhase.SETTLED:
                settled += value
                contribution = value
            elif event.phase is EconomicPhase.PENDING:
                pending += value
                contribution = value
            else:
                projected_only += value
                contribution = value
            if event.authorized_exception and contribution:
                authorized_exception += contribution
            if contribution:
                provenance.append(
                    {
                        "event_id": event.event_id,
                        "event_type": event.event_type,
                        "external_object_id": object_id,
                        "phase": event.phase.value,
                        "amount_minor_units": contribution,
                    }
                )
        total = settled + pending + projected_only
        return EconomicPosition(
            as_of=as_of,
            currency=currency,
            original_minor_units=original_minor_units,
            settled_minor_units=settled,
            pending_minor_units=pending,
            projected_only_minor_units=projected_only,
            projected_total_minor_units=total,
            projected_excess_minor_units=max(0, total - original_minor_units),
            authorized_exception_minor_units=authorized_exception,
            provenance=tuple(provenance),
        )

