"""Unit tests for the model registry."""
from __future__ import annotations

import textwrap

import pytest

from app.inference.registry import (
    AgentEntry,
    ModelChoice,
    ModelRegistry,
    RegistryError,
)


def _write(tmp_path, body: str):
    p = tmp_path / "registry.yaml"
    p.write_text(textwrap.dedent(body))
    return p


def test_loads_simple_registry(tmp_path):
    p = _write(
        tmp_path,
        """
        agents:
          facilitator:
            primary:
              provider: gemini
              model: gemini-3-pro
            fallback:
              - provider: featherless
                model: meta-llama-70b
            prompt_version: v1
            temperature: 0.4
            max_tokens: 1024
        """,
    )
    r = ModelRegistry(p)
    assert "facilitator" in r.list_agents()
    e = r.get("facilitator")
    assert e.primary.provider == "gemini"
    assert e.primary.model == "gemini-3-pro"
    assert e.fallback[0].provider == "featherless"
    assert e.prompt_version == "v1"
    assert e.temperature == pytest.approx(0.4)
    assert e.max_tokens == 1024
    assert e.chain == (
        ModelChoice("gemini", "gemini-3-pro"),
        ModelChoice("featherless", "meta-llama-70b"),
    )


def test_real_registry_file_loads():
    # The bundled config/models/atrio.yaml
    from pathlib import Path

    here = Path(__file__).resolve().parents[3] / "config" / "models" / "atrio.yaml"
    r = ModelRegistry(here)
    for agent in ("facilitator", "cfo", "cto", "cmo", "coo", "counsel", "treasury"):
        assert r.has(agent)


def test_missing_file(tmp_path):
    with pytest.raises(RegistryError):
        ModelRegistry(tmp_path / "no.yaml")


def test_invalid_yaml(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text(":\n:bad")
    with pytest.raises(RegistryError):
        ModelRegistry(p)


def test_missing_agents_mapping(tmp_path):
    p = _write(tmp_path, "other: 1")
    with pytest.raises(RegistryError, match="non-empty 'agents'"):
        ModelRegistry(p)


def test_agent_not_mapping(tmp_path):
    p = _write(tmp_path, "agents:\n  bad: 1")
    with pytest.raises(RegistryError, match="must be a mapping"):
        ModelRegistry(p)


def test_missing_primary(tmp_path):
    p = _write(
        tmp_path,
        """
        agents:
          x:
            fallback: []
            prompt_version: v1
        """,
    )
    with pytest.raises(RegistryError, match="missing primary"):
        ModelRegistry(p)


def test_missing_prompt_version(tmp_path):
    p = _write(
        tmp_path,
        """
        agents:
          x:
            primary: {provider: m, model: m}
        """,
    )
    with pytest.raises(RegistryError, match="prompt_version"):
        ModelRegistry(p)


def test_fallback_must_be_list(tmp_path):
    p = _write(
        tmp_path,
        """
        agents:
          x:
            primary: {provider: m, model: m}
            fallback: "nope"
            prompt_version: v1
        """,
    )
    with pytest.raises(RegistryError, match="fallback must be a list"):
        ModelRegistry(p)


def test_provider_must_be_string(tmp_path):
    p = _write(
        tmp_path,
        """
        agents:
          x:
            primary: {provider: 1, model: 2}
            prompt_version: v1
        """,
    )
    with pytest.raises(RegistryError, match="string 'provider'"):
        ModelRegistry(p)


def test_unknown_agent(tmp_path):
    p = _write(
        tmp_path,
        """
        agents:
          x:
            primary: {provider: m, model: m}
            prompt_version: v1
        """,
    )
    r = ModelRegistry(p)
    assert r.has("x") is True
    assert r.has("y") is False
    with pytest.raises(RegistryError):
        r.get("y")


def test_reload(tmp_path):
    p = _write(
        tmp_path,
        """
        agents:
          x:
            primary: {provider: m, model: a}
            prompt_version: v1
        """,
    )
    r = ModelRegistry(p)
    assert r.get("x").primary.model == "a"
    p.write_text(textwrap.dedent("""
        agents:
          x:
            primary: {provider: m, model: b}
            prompt_version: v1
    """))
    r.reload()
    assert r.get("x").primary.model == "b"


def test_choice_label():
    assert ModelChoice("p", "m").label() == "p/m"


def test_agent_entry_chain_primary_first():
    e = AgentEntry(
        agent_id="x",
        primary=ModelChoice("p1", "m1"),
        fallback=(ModelChoice("p2", "m2"), ModelChoice("p3", "m3")),
        prompt_version="v1",
    )
    assert e.chain[0].provider == "p1"
    assert e.chain[-1].provider == "p3"
