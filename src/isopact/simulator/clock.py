from __future__ import annotations

import heapq
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(order=True)
class _QueuedEvent:
    logical_time: int
    sequence: int
    event_id: str = field(compare=False)
    callback: Callable[[], None] = field(compare=False, repr=False)
    metadata: dict[str, Any] = field(compare=False, default_factory=dict)


class VirtualClock:
    def __init__(self) -> None:
        self.now = 0
        self._sequence = 0
        self._queue: list[_QueuedEvent] = []

    def schedule_at(
        self,
        logical_time: int,
        event_id: str,
        callback: Callable[[], None],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if logical_time < self.now:
            raise ValueError("cannot schedule an event in the logical past")
        self._sequence += 1
        heapq.heappush(
            self._queue,
            _QueuedEvent(logical_time, self._sequence, event_id, callback, metadata or {}),
        )

    def advance_to(self, logical_time: int) -> None:
        if logical_time < self.now:
            raise ValueError("virtual time is monotonic")
        while self._queue and self._queue[0].logical_time <= logical_time:
            queued = heapq.heappop(self._queue)
            self.now = queued.logical_time
            queued.callback()
        self.now = logical_time

    def run_until_idle(self) -> None:
        while self._queue:
            self.advance_to(self._queue[0].logical_time)

    def inspect_queue(self) -> list[dict[str, Any]]:
        return [
            {
                "event_id": item.event_id,
                "logical_time": item.logical_time,
                "sequence": item.sequence,
                "metadata": item.metadata,
            }
            for item in sorted(self._queue)
        ]

