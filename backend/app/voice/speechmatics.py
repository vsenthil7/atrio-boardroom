"""Speechmatics realtime STT client.

Connects to the Speechmatics Realtime API over WebSocket, streams 16-bit PCM
audio, and yields interim + final transcripts as they arrive.

Production deployment runs this inside the voice sidecar: the sidecar joins
the same LiveKit room as the user (using a "publisher" identity), subscribes
to the user's audio track, decodes Opus → PCM, and pipes the PCM frames to
this client. Transcripts get republished onto a LiveKit data channel so the
frontend renders captions in real time, and the final transcript becomes the
text of a new turn against POST /sessions/{id}/turns.

The client supports:
  - Custom dictionary (from config/dictionaries/demo_en.txt) for ATRIO terms
  - Language auto-detection across the BRD's 9 target languages
  - Backpressure: bounded queue, drops oldest audio if the network falls behind

Tests stub the WS layer; this module exposes a clean interface so the sidecar
can use it without depending on FastAPI.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from app.core.logging import get_logger

log = get_logger(__name__)

SPEECHMATICS_RT_URL = "wss://eu2.rt.speechmatics.com/v2"
DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "es", "fr", "de", "it", "pt", "nl", "pl", "tr")


@dataclass(frozen=True)
class Transcript:
    """A single transcript event from Speechmatics."""

    text: str
    is_final: bool
    language: str
    confidence: float
    start_time: float
    end_time: float
    speaker_id: str | None = None


@dataclass
class TranscriptionConfig:
    """Per-session STT config."""

    language: str = DEFAULT_LANGUAGE
    enable_partials: bool = True
    custom_dictionary: list[str] = field(default_factory=list)
    diarization: bool = False
    operating_point: str = "enhanced"  # 'standard' or 'enhanced'

    def to_speechmatics_payload(self) -> dict[str, Any]:
        """Render the StartRecognition message body Speechmatics expects."""
        config: dict[str, Any] = {
            "type": "StartRecognition",
            "audio_format": {
                "type": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": 16000,
            },
            "transcription_config": {
                "language": self.language,
                "enable_partials": self.enable_partials,
                "operating_point": self.operating_point,
            },
        }
        if self.diarization:
            config["transcription_config"]["diarization"] = "speaker"
        if self.custom_dictionary:
            config["transcription_config"]["additional_vocab"] = [
                {"content": term} for term in self.custom_dictionary
            ]
        return config


class _WebSocketProtocol(Protocol):
    """Subset of `websockets` we use — keeps the module testable."""

    async def send(self, message: str | bytes) -> None: ...
    async def recv(self) -> str | bytes: ...
    async def close(self) -> None: ...


class SpeechmaticsClient:
    """Realtime STT client.

    Lifecycle:
        async with SpeechmaticsClient(api_key, config) as client:
            async for transcript in client.transcribe(audio_stream):
                ...

    The constructor accepts an `open_websocket` callable so tests can inject
    a fake transport. In production it's the `websockets.connect` coroutine.
    """

    def __init__(
        self,
        api_key: str,
        config: TranscriptionConfig | None = None,
        open_websocket: Any = None,
    ) -> None:
        self.api_key = api_key
        self.config = config or TranscriptionConfig()
        self._open_websocket = open_websocket
        self._ws: _WebSocketProtocol | None = None
        self._seq_no = 0

    async def __aenter__(self) -> SpeechmaticsClient:
        await self._connect()
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.close()

    async def _connect(self) -> None:
        """Open the WS and send the StartRecognition handshake."""
        if self._open_websocket is None:
            try:
                import websockets  # noqa: PLC0415  - optional dep
            except ImportError as e:
                raise RuntimeError(
                    "websockets package required for live Speechmatics. "
                    "Install with: pip install websockets"
                ) from e
            self._open_websocket = websockets.connect

        headers = {"Authorization": f"Bearer {self.api_key}"}
        self._ws = await self._open_websocket(
            SPEECHMATICS_RT_URL,
            additional_headers=headers,
            max_size=2**24,  # 16 MB messages
        )
        await self._ws.send(json.dumps(self.config.to_speechmatics_payload()))
        # Wait for RecognitionStarted ack
        ack = await self._ws.recv()
        if isinstance(ack, bytes):
            ack = ack.decode()
        msg = json.loads(ack)
        if msg.get("message") != "RecognitionStarted":
            raise RuntimeError(f"speechmatics handshake failed: {msg}")
        log.info(
            "speechmatics_started",
            language=self.config.language,
            partials=self.config.enable_partials,
        )

    async def send_audio(self, pcm_chunk: bytes) -> None:
        """Send a PCM s16le chunk (typically 100ms = 3200 bytes at 16 kHz mono)."""
        if self._ws is None:
            raise RuntimeError("not connected — use `async with` block")
        await self._ws.send(pcm_chunk)
        self._seq_no += 1

    async def end_of_stream(self) -> None:
        """Tell Speechmatics no more audio is coming."""
        if self._ws is None:
            return
        await self._ws.send(
            json.dumps({"message": "EndOfStream", "last_seq_no": self._seq_no})
        )

    async def transcripts(self) -> AsyncIterator[Transcript]:
        """Yield transcripts as they arrive."""
        if self._ws is None:
            raise RuntimeError("not connected")
        while True:
            try:
                raw = await self._ws.recv()
            except Exception:  # noqa: BLE001 — any exception means stream closed
                break
            if isinstance(raw, bytes):
                raw = raw.decode()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            t = _parse_transcript(msg, self.config.language)
            if t is not None:
                yield t
            if msg.get("message") == "EndOfTranscript":
                break

    async def close(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001
                pass
            self._ws = None


def _parse_transcript(msg: dict[str, Any], default_lang: str) -> Transcript | None:
    """Turn a Speechmatics message into our internal Transcript shape."""
    kind = msg.get("message")
    if kind not in ("AddTranscript", "AddPartialTranscript"):
        return None
    is_final = kind == "AddTranscript"
    results = msg.get("results", []) or []
    if not results:
        return None
    text = " ".join(
        (r.get("alternatives") or [{}])[0].get("content", "") for r in results
    ).strip()
    if not text:
        return None
    confidence = float(
        (results[0].get("alternatives") or [{}])[0].get("confidence", 1.0)
    )
    start_time = float(results[0].get("start_time", 0.0))
    end_time = float(results[-1].get("end_time", start_time))
    speaker_id = (results[0].get("alternatives") or [{}])[0].get("speaker")
    metadata = msg.get("metadata", {}) or {}
    language = metadata.get("language", default_lang)
    return Transcript(
        text=text,
        is_final=is_final,
        language=language,
        confidence=confidence,
        start_time=start_time,
        end_time=end_time,
        speaker_id=speaker_id,
    )


def load_custom_dictionary(dictionary_path: Path | str) -> list[str]:
    """Read the ATRIO domain-term list (one term per line, # comments ok)."""
    p = Path(dictionary_path)
    if not p.exists():
        return []
    terms: list[str] = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        terms.append(line)
    return terms


# ----------------------------------------------------------------------------
# Audio plumbing helpers — used by the sidecar to wire LiveKit ↔ Speechmatics
# ----------------------------------------------------------------------------


class AudioBuffer:
    """Bounded audio buffer for the LiveKit → Speechmatics bridge.

    Drops oldest frames if the consumer falls behind (>2 s of audio queued at
    16kHz s16le → 64 kB). Drops are logged with a counter the sidecar
    publishes to Prometheus.
    """

    MAX_BUFFERED_BYTES = 64_000

    def __init__(self) -> None:
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.dropped_chunks = 0
        self._buffered_bytes = 0

    async def put(self, chunk: bytes) -> None:
        if self._buffered_bytes + len(chunk) > self.MAX_BUFFERED_BYTES:
            # Drop oldest frames until we fit
            while (
                not self._queue.empty()
                and self._buffered_bytes + len(chunk) > self.MAX_BUFFERED_BYTES
            ):
                old = self._queue.get_nowait()
                self._buffered_bytes -= len(old)
                self.dropped_chunks += 1
        await self._queue.put(chunk)
        self._buffered_bytes += len(chunk)

    async def get(self) -> bytes:
        chunk = await self._queue.get()
        self._buffered_bytes -= len(chunk)
        return chunk

    def empty(self) -> bool:
        return self._queue.empty()
