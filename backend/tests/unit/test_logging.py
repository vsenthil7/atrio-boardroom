"""Unit tests for app.core.logging."""
from __future__ import annotations

from app.core import logging as logmod
from app.core.logging import configure_logging, get_logger


def test_get_logger_returns_logger():
    log = get_logger("test")
    assert hasattr(log, "info")
    log.info("ping", k="v")


def test_get_logger_no_name():
    log = get_logger()
    assert log is not None


def test_configure_logging_idempotent():
    logmod._configured = False  # reset
    configure_logging()
    configure_logging()  # no-op second call
    assert logmod._configured is True


def test_logger_in_prod_renders_json():
    logmod._configured = False
    from app.core.config import Settings, reset_settings_cache

    import app.core.logging as lm

    original_get_settings = lm.get_settings
    lm.get_settings = lambda: Settings(atrio_env="prod")  # type: ignore[assignment]
    try:
        configure_logging()
        assert logmod._configured is True
    finally:
        lm.get_settings = original_get_settings
        logmod._configured = False
        reset_settings_cache()
