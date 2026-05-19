"""Tests for the voice sidecar bridge logic."""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

import pytest

# Make the sidecar importable
SIDECAR_ROOT = Path(__file__).resolve().parents[3] / "sidecars"
if str(SIDECAR_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(SIDECAR_ROOT.parent))

from sidecars.voice.__main__ import (  # noqa: E402
    SessionBridge,
    Sidecar,
    SidecarConfig,
)

from app.voice.speechmatics import Transcript  # noqa: E402


# ---------------------------------------------------------------- config


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("ATRIO_API_BASE_URL", "http://x:8000/api/v1")
    monkeypatch.setenv("LIVEKIT_URL", "ws://lk:7880")
    monkeypatch.setenv("SPEECHMATICS_API_KEY", "sk-test")
    cfg = SidecarConfig.from_env()
    assert cfg.api_base_url == "http://x:8000/api/v1"
    assert cfg.livekit_url == "ws://lk:7880"
    assert cfg.speechmatics_api_key == "sk-test"


def test_config_defaults_when_env_missing(monkeypatch):
    for k in ("ATRIO_API_BASE_URL", "LIVEKIT_URL", "LIVEKIT_API_KEY",
              "LIVEKIT_API_SECRET", "SPEECHMATICS_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    cfg = SidecarConfig.from_env()
    assert cfg.api_base_url == "http://api:8000/api/v1"
    assert cfg.speechmatics_api_key == ""


# ---------------------------------------------------------------- bridge


def _bridge(**overrides) -> SessionBridge:
    cfg = SidecarConfig(final_transcript_silence_ms=800)
    return SessionBridge(
        session_id="s1",
        user_access_token="t",
        config=cfg,
        **overrides,
    )


def _t(text: str, *, is_final: bool, speaker: str = "U1") -> Transcript:
    return Transcript(
        text=text,
        is_final=is_final,
        language="en",
        confidence=0.95,
        start_time=0.0,
        end_time=0.5,
        speaker_id=speaker,
    )


async def test_handle_transcript_publishes_caption():
    published: list[dict] = []

    async def pub(payload):
        published.append(payload)

    b = _bridge(publish_caption_fn=pub)
    await b._handle_transcript(_t("hello world", is_final=False))
    assert len(published) == 1
    assert published[0]["kind"] == "caption"
    assert published[0]["text"] == "hello world"
    assert published[0]["is_final"] is False


async def test_handle_final_transcript_does_not_post_immediately():
    posted = []

    async def post(api, tok, sid, text):
        posted.append((sid, text))

    b = _bridge(post_turn_fn=post)
    await b._handle_transcript(_t("hi", is_final=True))
    # No immediate post — must wait for silence
    assert posted == []
    assert b.pending_text_parts == ["hi"]


async def test_silence_flush_posts_turn():
    posted = []

    async def post(api, tok, sid, text):
        posted.append((sid, text))

    b = _bridge(post_turn_fn=post)
    b.config.final_transcript_silence_ms = 50
    await b._handle_transcript(_t("hello", is_final=True))
    # Wait long enough for silence to elapse
    await asyncio.sleep(0.08)
    flushed = await b.maybe_flush()
    assert flushed is True
    assert posted == [("s1", "hello")]
    # Pending text reset
    assert b.pending_text_parts == []


async def test_silence_flush_combines_multiple_finals():
    posted = []

    async def post(api, tok, sid, text):
        posted.append(text)

    b = _bridge(post_turn_fn=post)
    b.config.final_transcript_silence_ms = 50
    await b._handle_transcript(_t("hello", is_final=True))
    await b._handle_transcript(_t("there", is_final=True))
    await asyncio.sleep(0.08)
    await b.maybe_flush()
    assert posted == ["hello there"]


async def test_maybe_flush_returns_false_when_no_pending():
    b = _bridge(post_turn_fn=lambda *a: asyncio.sleep(0))
    assert (await b.maybe_flush()) is False


async def test_maybe_flush_returns_false_during_active_speech():
    posted = []

    async def post(api, tok, sid, text):
        posted.append(text)

    b = _bridge(post_turn_fn=post)
    b.config.final_transcript_silence_ms = 1000
    await b._handle_transcript(_t("hello", is_final=True))
    assert (await b.maybe_flush()) is False
    assert posted == []


async def test_partial_transcript_not_added_to_pending():
    b = _bridge()
    await b._handle_transcript(_t("hel", is_final=False))
    assert b.pending_text_parts == []


# ---------------------------------------------------------------- sidecar


async def test_sidecar_add_and_remove_bridge():
    cfg = SidecarConfig()
    s = Sidecar(cfg)
    b = s.add_bridge("session-a", "token-a")
    assert "session-a" in s.bridges
    assert b.session_id == "session-a"
    s.remove_bridge("session-a")
    assert "session-a" not in s.bridges


async def test_sidecar_remove_unknown_session_no_error():
    s = Sidecar(SidecarConfig())
    s.remove_bridge("nope")  # must not raise


async def test_sidecar_shutdown_clears_bridges():
    s = Sidecar(SidecarConfig())
    s.add_bridge("a", "t")
    s.add_bridge("b", "t")
    await s.shutdown()
    assert s.bridges == {}
    assert s._stop.is_set()


async def test_silence_watcher_calls_maybe_flush():
    s = Sidecar(SidecarConfig(poll_interval_s=0.01))
    b = s.add_bridge("x", "t")
    b.config.final_transcript_silence_ms = 5
    flushed_count = 0

    async def post(*a):
        nonlocal flushed_count
        flushed_count += 1

    b.post_turn_fn = post
    # Seed pending text + recent timestamp
    b.pending_text_parts = ["hi"]
    b.last_final_ts = time.monotonic() - 1.0  # already silent

    task = asyncio.create_task(s._silence_watcher(b))
    await asyncio.sleep(0.05)
    s._stop.set()
    await task
    assert flushed_count >= 1
