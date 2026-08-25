from __future__ import annotations

from typing import Any, Protocol

from .models import InterceptionDecision, ScheduledAction


class InterceptionPort(Protocol):
    def intercept(self, action: ScheduledAction) -> InterceptionDecision: ...

    def after_external_call(
        self, action: ScheduledAction, result: dict[str, Any]
    ) -> None: ...


class AllowAllInterceptor:
    def intercept(self, action: ScheduledAction) -> InterceptionDecision:
        return InterceptionDecision("ALLOW", "UNMANAGED_ALLOW_ALL")

    def after_external_call(
        self, action: ScheduledAction, result: dict[str, Any]
    ) -> None:
        return None
