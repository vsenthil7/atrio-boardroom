"""Model registry — reads `config/models/atrio.yaml` for agent→provider routing.

P5 implementation: every inference invocation reads the registry; no code path
hardcodes a model name. Hot-reload is supported via `reload()`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.core.config import get_settings


class RegistryError(Exception):
    """Raised when the registry file cannot be loaded or is malformed."""


@dataclass(frozen=True)
class ModelChoice:
    """A single provider+model selection."""

    provider: str
    model: str

    def label(self) -> str:
        return f"{self.provider}/{self.model}"


@dataclass(frozen=True)
class AgentEntry:
    """Registry entry for one agent: a primary and an ordered fallback chain."""

    agent_id: str
    primary: ModelChoice
    fallback: tuple[ModelChoice, ...]
    prompt_version: str
    temperature: float = 0.7
    max_tokens: int = 1024
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def chain(self) -> tuple[ModelChoice, ...]:
        """Full ordered chain: primary first, then fallbacks."""
        return (self.primary, *self.fallback)


class ModelRegistry:
    """In-memory model registry loaded from YAML."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else Path(get_settings().model_registry_path)
        self._agents: dict[str, AgentEntry] = {}
        self.load()

    def load(self) -> None:
        """Load (or reload) the registry from disk."""
        if not self._path.exists():
            raise RegistryError(f"Model registry not found: {self._path}")
        try:
            raw = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            raise RegistryError(f"Invalid YAML in registry: {e}") from e

        agents_raw = raw.get("agents")
        if not isinstance(agents_raw, dict) or not agents_raw:
            raise RegistryError("Registry must contain a non-empty 'agents' mapping")

        agents: dict[str, AgentEntry] = {}
        for agent_id, body in agents_raw.items():
            agents[agent_id] = self._parse_agent(agent_id, body)
        self._agents = agents

    def reload(self) -> None:
        self.load()

    def _parse_agent(self, agent_id: str, body: Any) -> AgentEntry:
        if not isinstance(body, dict):
            raise RegistryError(f"Agent '{agent_id}' must be a mapping")
        primary_raw = body.get("primary")
        if not isinstance(primary_raw, dict):
            raise RegistryError(f"Agent '{agent_id}' is missing primary")
        primary = self._parse_choice(agent_id, primary_raw, "primary")

        fb_raw = body.get("fallback", []) or []
        if not isinstance(fb_raw, list):
            raise RegistryError(f"Agent '{agent_id}' fallback must be a list")
        fallback = tuple(self._parse_choice(agent_id, c, "fallback") for c in fb_raw)

        prompt_version = body.get("prompt_version")
        if not isinstance(prompt_version, str) or not prompt_version:
            raise RegistryError(f"Agent '{agent_id}' missing prompt_version")

        temperature = float(body.get("temperature", 0.7))
        max_tokens = int(body.get("max_tokens", 1024))
        metadata = body.get("metadata", {}) or {}

        return AgentEntry(
            agent_id=agent_id,
            primary=primary,
            fallback=fallback,
            prompt_version=prompt_version,
            temperature=temperature,
            max_tokens=max_tokens,
            metadata=dict(metadata),
        )

    @staticmethod
    def _parse_choice(agent_id: str, body: Any, where: str) -> ModelChoice:
        if not isinstance(body, dict):
            raise RegistryError(f"Agent '{agent_id}' {where} must be a mapping")
        provider = body.get("provider")
        model = body.get("model")
        if not isinstance(provider, str) or not isinstance(model, str):
            raise RegistryError(
                f"Agent '{agent_id}' {where} must have string 'provider' and 'model'"
            )
        return ModelChoice(provider=provider, model=model)

    # ---------------------------------------------------------------- API

    def list_agents(self) -> list[str]:
        return sorted(self._agents.keys())

    def get(self, agent_id: str) -> AgentEntry:
        try:
            return self._agents[agent_id]
        except KeyError as e:
            raise RegistryError(f"Unknown agent: {agent_id}") from e

    def has(self, agent_id: str) -> bool:
        return agent_id in self._agents
