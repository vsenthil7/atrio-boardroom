"""Unit tests for app.core.config."""
from __future__ import annotations

import os

import pytest

from app.core.config import Settings, get_settings, project_root, reset_settings_cache


def test_settings_defaults_loaded():
    s = Settings()
    assert s.atrio_env in {"local", "test", "staging", "demo", "prod"}
    assert s.jwt_algorithm == "RS256"


def test_settings_is_test_and_is_prod_like():
    reset_settings_cache()
    s = Settings(atrio_env="test")
    assert s.is_test is True
    assert s.is_prod_like is False
    s2 = Settings(atrio_env="prod")
    assert s2.is_prod_like is True
    assert s2.is_test is False


def test_cors_origin_list_stripped():
    s = Settings(cors_origins=" http://a.com , http://b.com ,  , http://c.com")
    assert s.cors_origin_list == ["http://a.com", "http://b.com", "http://c.com"]


def test_get_settings_cached(monkeypatch):
    reset_settings_cache()
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
    reset_settings_cache()
    s3 = get_settings()
    assert s3 is not s1


def test_project_root_exists():
    p = project_root()
    assert p.exists()
    assert p.is_dir()


@pytest.mark.parametrize("env", ["local", "test", "staging", "demo", "prod"])
def test_all_envs_acceptable(env):
    s = Settings(atrio_env=env)  # type: ignore[arg-type]
    assert s.atrio_env == env
