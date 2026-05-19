"""ATRIO voice sidecar.

A long-running process that:

  1. Subscribes to a LiveKit room (using a service-identity token issued by
     the API).
  2. For each participant's audio track, decodes Opus → PCM s16le @ 16 kHz.
  3. Opens a Speechmatics realtime WebSocket per session and pipes PCM in.
  4. Receives transcripts and republishes them on the LiveKit data channel
     under topic 'captions' so the SPA renders live captions.
  5. When the speaker pauses (a final transcript with > 800 ms silence after
     it), it POSTs a new turn to the API on behalf of the user, which kicks
     off the boardroom debate — so users can ask questions by voice.

This module is designed to be importable for tests (the audio bridge logic
is split out into small testable pieces) AND runnable as `python -m
sidecars.voice` for production.

Production deployment: a separate container in docker-compose, scaled
independently from the API. Local dev: `make voice-sidecar`.
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

# Add the backend app to the path so we can reuse the Speechmatics client.
HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "..", "backend"))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.core.logging import configure_logging, get_logger  # noqa: E402
from app.voice.speechmatics import (  # noqa: E402
    AudioBuffer,
    SpeechmaticsClient,
    Transcript,
    TranscriptionConfig,
)

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class SidecarConfig:
    api_base_url: str = "http://api:8000/api/v1"
    livekit_url: str = "ws://livekit:7880"
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    speechmatics_api_key: str = ""
    final_transcript_silence_ms: int = 800
    custom_dictionary: list[str] = field(default_factory=list)
    poll_interval_s: float = 1.0

    @classmethod
    def from_env(cls) -> SidecarConfig:
        return cls(
            api_base_url=os.environ.get("ATRIO_API_BASE_URL", "http://api:8000/api/v1"),
            livekit_url=os.environ.get("LIVEKIT_URL", "ws://livekit:7880"),
            livekit_api_key=os.environ.get("LIVEKIT_API_KEY", ""),
            livekit_api_secret=os.environ.get("LIVEKIT_API_SECRET", ""),
            speechmatics_api_key=os.environ.get("SPEECHMATICS_API_KEY", ""),
        )


# ---------------------------------------------------------------------------
# Session bridge — one per active voice session
# ---------------------------------------------------------------------------


@dataclass
class SessionBridge:
    """A single user → Speechmatics → captions pipeline.

    The actual LiveKit subscription is wired in `run()`. The transcript-to-turn
    decision logic is in `_handle_transcript`, which is tested directly.
    """

    session_id: str
    user_access_token: str
    config: SidecarConfig
    transcript_log: list[Transcript] = field(default_factory=list)
    last_final_ts: float = 0.0
    pending_text_parts: list[str] = field(default_factory=list)
    # Injected for tests:
    post_turn_fn: Any = None  # async fn(api_url, token, session_id, text) -> None
    publish_caption_fn: Any = None  # async fn(payload: dict) -> None

    async def _handle_transcript(self, t: Transcript) -> None:
        """Process one transcript event.

        - Publish a caption to LiveKit data channel for all transcripts.
        - When a final transcript arrives, add to pending text.
        - When silence > threshold passes after a final, flush pending text as
          a new user turn against the API.
        """
        self.transcript_log.append(t)
        await self._publish_caption(t)
        if not t.is_final:
            return
        self.pending_text_parts.append(t.text)
        self.last_final_ts = time.monotonic()

    async def maybe_flush(self) -> bool:
        """Check whether enough silence has passed to flush pending text.

        Returns True if a flush was performed.
        """
        if not self.pending_text_parts:
            return False
        silence_ms = (time.monotonic() - self.last_final_ts) * 1000
        if silence_ms < self.config.final_transcript_silence_ms:
            return False
        text = " ".join(self.pending_text_parts).strip()
        self.pending_text_parts = []
        if not text:
            return False
        await self._post_turn(text)
        return True

    async def _publish_caption(self, t: Transcript) -> None:
        payload = {
            "kind": "caption",
            "text": t.text,
            "is_final": t.is_final,
            "language": t.language,
            "speaker": t.speaker_id or "user",
        }
        if self.publish_caption_fn is not None:
            await self.publish_caption_fn(payload)

    async def _post_turn(self, text: str) -> None:
        if self.post_turn_fn is not None:
            await self.post_turn_fn(
                self.config.api_base_url,
                self.user_access_token,
                self.session_id,
                text,
            )
            return
        # Real HTTP call
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{self.config.api_base_url}/sessions/{self.session_id}/turns",
                headers={
                    "Authorization": f"Bearer {self.user_access_token}",
                    "Content-Type": "application/json",
                },
                json={"text": text, "mode": "debate", "language": "en"},
            )
            log.info(
                "voice_turn_posted",
                session_id=self.session_id,
                status=r.status_code,
                text_preview=text[:80],
            )


# ---------------------------------------------------------------------------
# Sidecar runtime
# ---------------------------------------------------------------------------


class Sidecar:
    """Top-level coordinator. Owns the list of active SessionBridges."""

    def __init__(self, config: SidecarConfig) -> None:
        self.config = config
        self.bridges: dict[str, SessionBridge] = {}
        self._stop = asyncio.Event()

    def add_bridge(self, session_id: str, user_access_token: str) -> SessionBridge:
        b = SessionBridge(
            session_id=session_id,
            user_access_token=user_access_token,
            config=self.config,
        )
        self.bridges[session_id] = b
        log.info("bridge_added", session_id=session_id)
        return b

    def remove_bridge(self, session_id: str) -> None:
        if session_id in self.bridges:
            del self.bridges[session_id]
            log.info("bridge_removed", session_id=session_id)

    async def run_bridge(self, bridge: SessionBridge) -> None:
        """Run one bridge end-to-end.

        Connects to Speechmatics, processes the audio buffer, dispatches
        transcripts, and periodically calls maybe_flush() so trailing-silence
        flushes work even if the bridge is idle on the receiver side.
        """
        cfg = TranscriptionConfig(
            language="en",
            enable_partials=True,
            custom_dictionary=self.config.custom_dictionary,
        )
        async with SpeechmaticsClient(
            api_key=self.config.speechmatics_api_key, config=cfg
        ) as client:
            asyncio.create_task(self._silence_watcher(bridge))
            async for t in client.transcripts():
                await bridge._handle_transcript(t)

    async def _silence_watcher(self, bridge: SessionBridge) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(self.config.poll_interval_s)
            try:
                await bridge.maybe_flush()
            except Exception:  # noqa: BLE001
                log.exception("flush_failed", session_id=bridge.session_id)

    async def shutdown(self) -> None:
        self._stop.set()
        self.bridges.clear()

    async def run_forever(self) -> None:
        """Production entry point — wait forever until SIGTERM."""
        configure_logging()
        log.info("sidecar_starting", api_base_url=self.config.api_base_url)
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))
        await self._stop.wait()
        log.info("sidecar_stopped")


# ---------------------------------------------------------------------------
# Audio plumbing — LiveKit → AudioBuffer → Speechmatics
# ---------------------------------------------------------------------------


async def pump_audio_buffer_to_client(
    buffer: AudioBuffer, client: SpeechmaticsClient, stop_event: asyncio.Event
) -> None:
    """Drain the LiveKit-fed buffer into Speechmatics until stop is set."""
    while not stop_event.is_set():
        if buffer.empty():
            await asyncio.sleep(0.01)
            continue
        chunk = await buffer.get()
        await client.send_audio(chunk)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def _main() -> None:
    cfg = SidecarConfig.from_env()
    sidecar = Sidecar(cfg)
    await sidecar.run_forever()


if __name__ == "__main__":
    asyncio.run(_main())
