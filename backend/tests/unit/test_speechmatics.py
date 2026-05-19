"""Unit tests for SpeechmaticsClient + helpers.

We use a fake WS to exercise the full lifecycle without network.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.voice.speechmatics import (
    AudioBuffer,
    SpeechmaticsClient,
    TranscriptionConfig,
    _parse_transcript,
    load_custom_dictionary,
)


class _FakeWS:
    """In-memory WS for tests."""

    def __init__(self, server_messages: list[str | bytes]) -> None:
        self._inbox: asyncio.Queue[str | bytes] = asyncio.Queue()
        for m in server_messages:
            self._inbox.put_nowait(m)
        self.sent: list[Any] = []
        self.closed = False

    async def send(self, message: str | bytes) -> None:
        self.sent.append(message)

    async def recv(self) -> str | bytes:
        if self._inbox.empty():
            await asyncio.sleep(0.001)
            raise ConnectionError("stream closed")
        return await self._inbox.get()

    async def close(self) -> None:
        self.closed = True


def _make_open_ws(messages: list[str | bytes]):
    async def open_ws(*_args: Any, **_kwargs: Any) -> _FakeWS:
        return _FakeWS(messages)

    return open_ws


# ---------------------------------------------------------------- config


def test_config_renders_speechmatics_payload():
    cfg = TranscriptionConfig(
        language="en",
        enable_partials=True,
        custom_dictionary=["ATRIO", "xStock"],
        diarization=True,
        operating_point="enhanced",
    )
    p = cfg.to_speechmatics_payload()
    assert p["type"] == "StartRecognition"
    assert p["audio_format"]["sample_rate"] == 16000
    assert p["transcription_config"]["language"] == "en"
    assert p["transcription_config"]["diarization"] == "speaker"
    assert p["transcription_config"]["enable_partials"] is True
    assert {"content": "ATRIO"} in p["transcription_config"]["additional_vocab"]


def test_config_minimal_no_diarization_no_vocab():
    cfg = TranscriptionConfig()
    p = cfg.to_speechmatics_payload()
    assert "diarization" not in p["transcription_config"]
    assert "additional_vocab" not in p["transcription_config"]


# ---------------------------------------------------------------- transcript parser


def test_parse_transcript_final():
    msg = {
        "message": "AddTranscript",
        "results": [
            {
                "start_time": 0.1,
                "end_time": 0.4,
                "alternatives": [
                    {"content": "hello", "confidence": 0.97, "speaker": "S1"}
                ],
            },
            {
                "start_time": 0.5,
                "end_time": 0.8,
                "alternatives": [{"content": "world", "confidence": 0.94}],
            },
        ],
        "metadata": {"language": "en"},
    }
    t = _parse_transcript(msg, "en")
    assert t is not None
    assert t.is_final is True
    assert t.text == "hello world"
    assert t.start_time == pytest.approx(0.1)
    assert t.end_time == pytest.approx(0.8)
    assert t.speaker_id == "S1"
    assert t.confidence == pytest.approx(0.97)


def test_parse_partial_transcript():
    msg = {
        "message": "AddPartialTranscript",
        "results": [
            {
                "start_time": 0.0,
                "end_time": 0.2,
                "alternatives": [{"content": "hel"}],
            }
        ],
    }
    t = _parse_transcript(msg, "en")
    assert t is not None
    assert t.is_final is False


def test_parse_ignores_other_messages():
    assert _parse_transcript({"message": "RecognitionStarted"}, "en") is None
    assert _parse_transcript({"message": "Info"}, "en") is None


def test_parse_empty_results():
    assert _parse_transcript({"message": "AddTranscript", "results": []}, "en") is None
    assert (
        _parse_transcript(
            {
                "message": "AddTranscript",
                "results": [{"alternatives": [{"content": "   "}]}],
            },
            "en",
        )
        is None
    )


# ---------------------------------------------------------------- client lifecycle


async def test_client_handshake_then_transcripts():
    messages = [
        json.dumps({"message": "RecognitionStarted"}),
        json.dumps(
            {
                "message": "AddTranscript",
                "results": [
                    {
                        "start_time": 0.0,
                        "end_time": 0.3,
                        "alternatives": [{"content": "hello", "confidence": 0.9}],
                    }
                ],
                "metadata": {"language": "en"},
            }
        ),
        json.dumps({"message": "EndOfTranscript"}),
    ]
    client = SpeechmaticsClient(
        api_key="test-key",
        config=TranscriptionConfig(language="en"),
        open_websocket=_make_open_ws(messages),
    )
    async with client:
        await client.send_audio(b"\x00" * 3200)
        await client.end_of_stream()
        out = [t async for t in client.transcripts()]
    assert len(out) == 1
    assert out[0].text == "hello"


async def test_client_handshake_failure_raises():
    messages = [json.dumps({"message": "Error", "reason": "bad key"})]
    client = SpeechmaticsClient(
        api_key="bad",
        open_websocket=_make_open_ws(messages),
    )
    with pytest.raises(RuntimeError, match="handshake failed"):
        await client._connect()


async def test_client_close_is_idempotent():
    client = SpeechmaticsClient(
        api_key="k",
        open_websocket=_make_open_ws([json.dumps({"message": "RecognitionStarted"})]),
    )
    await client._connect()
    await client.close()
    await client.close()  # second call must not raise


async def test_send_audio_without_connection_raises():
    client = SpeechmaticsClient(api_key="k")
    with pytest.raises(RuntimeError, match="not connected"):
        await client.send_audio(b"x")


async def test_transcripts_without_connection_raises():
    client = SpeechmaticsClient(api_key="k")
    with pytest.raises(RuntimeError, match="not connected"):
        async for _ in client.transcripts():
            pass


async def test_end_of_stream_without_connection_is_noop():
    client = SpeechmaticsClient(api_key="k")
    await client.end_of_stream()  # must not raise


# ---------------------------------------------------------------- custom dictionary


def test_load_dictionary(tmp_path):
    p = tmp_path / "d.txt"
    p.write_text(
        "# header comment\nATRIO\n\nxStock\n  whitespace term  \n# trailing comment\n"
    )
    terms = load_custom_dictionary(p)
    assert terms == ["ATRIO", "xStock", "whitespace term"]


def test_load_dictionary_missing_returns_empty(tmp_path):
    assert load_custom_dictionary(tmp_path / "nope.txt") == []


def test_load_real_demo_dictionary():
    from pathlib import Path

    p = Path(__file__).resolve().parents[3] / "config" / "dictionaries" / "demo_en.txt"
    terms = load_custom_dictionary(p)
    assert "ATRIO" in terms
    assert any("xStock" in t for t in terms)


# ---------------------------------------------------------------- audio buffer


async def test_audio_buffer_round_trip():
    buf = AudioBuffer()
    await buf.put(b"\x00\x01")
    await buf.put(b"\x02\x03")
    assert (await buf.get()) == b"\x00\x01"
    assert (await buf.get()) == b"\x02\x03"
    assert buf.empty()


async def test_audio_buffer_drops_old_when_full():
    buf = AudioBuffer()
    # Fill way past the limit
    big = b"\x00" * 32_000
    await buf.put(big)
    await buf.put(big)
    await buf.put(big)  # one more pushes over MAX
    # Drops happened
    assert buf.dropped_chunks >= 1
    # Buffer still has the most recent data
    assert not buf.empty()
