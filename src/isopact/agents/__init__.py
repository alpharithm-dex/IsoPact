from .models import AgentIdentity, AgentRole, Capability

__all__ = ["AgentIdentity", "AgentRole", "AgentToolRuntime", "Capability", "build_adk_fleet", "build_deployment_agent"]


def __getattr__(name: str):
    """Keep control-plane modules importable without the optional ADK runtime."""
    if name in {"build_adk_fleet", "build_deployment_agent"}:
        from .fleet import build_adk_fleet, build_deployment_agent

        return {"build_adk_fleet": build_adk_fleet, "build_deployment_agent": build_deployment_agent}[name]
    if name == "AgentToolRuntime":
        from .runtime import AgentToolRuntime

        return AgentToolRuntime
    raise AttributeError(name)
