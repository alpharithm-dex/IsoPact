from __future__ import annotations

from .models import AgentIdentity, CAPABILITY_MATRIX, Capability


class AgentCapabilityDenied(PermissionError): pass


class AgentCapabilityPolicy:
    model_calls = 0

    @staticmethod
    def authorize(identity: AgentIdentity, capability: Capability) -> None:
        if capability not in CAPABILITY_MATRIX[identity.role]:
            raise AgentCapabilityDenied(f"{identity.agent_id} role {identity.role.value} lacks {capability.value}")

    @staticmethod
    def inventory(identity: AgentIdentity) -> tuple[str, ...]:
        return tuple(sorted(item.value for item in CAPABILITY_MATRIX[identity.role]))
