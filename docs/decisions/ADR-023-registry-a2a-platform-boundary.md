# ADR-023: Registry, A2A, and platform boundary

Status: Accepted

## Decision

Treat automatic Agent Registry entries for the four Google ADK Runtime agents
as valid CUSTOM/non-A2A catalog entries. Empty A2A skill arrays are expected and
will not be fabricated. A2A is claimed only for a genuine live A2A endpoint.

The prior genuine `A2aAgent` Runtime deployment attempt remains recorded in
`artifacts/agents/support-a2a-deployment.json`; the platform rejected
`a2a_extension`. A2A is therefore not claimed and does not block Stage 8B.

Four capability packages exist separately as versioned `SKILL.md` packages.
Authenticated Skill Registry `ListSkills` calls timed out in three documented
regions, including a 120-second retry, while Agent Registry worked. Therefore
no live skill resource ID, revision, attachment, or search result is claimed.
Runtime agents remain discoverable in Agent Registry; local skill packages are
prepared for registration when that API responds.

