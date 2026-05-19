"""Integration tests for POST /sessions/{id}/turns (SSE streaming)."""
from __future__ import annotations

import json
from typing import Iterator


def _parse_sse(body: str) -> Iterator[tuple[str, dict]]:
    """Parse SSE 'event:'+'data:' blocks separated by blank lines."""
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        event = None
        data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = line.split(":", 1)[1].strip()
        if event and data:
            try:
                yield event, json.loads(data)
            except json.JSONDecodeError:
                yield event, {"raw": data}


async def _open_session(client, header, title="t"):
    r = await client.post("/api/v1/sessions", headers=header, json={"title": title})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_turn_stream_single_mode_emits_all_event_types(app_client, auth_header):
    sid = await _open_session(app_client, auth_header)
    r = await app_client.post(
        f"/api/v1/sessions/{sid}/turns",
        headers=auth_header,
        json={"text": "Should we hire 4 engineers?", "language": "en", "mode": "single"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = list(_parse_sse(r.text))
    assert events, f"no events parsed from body: {r.text[:400]}"
    kinds = [k for k, _ in events]
    assert "turn_started" in kinds
    assert "agent_done" in kinds
    assert "consensus" in kinds
    assert kinds[-1] == "stream_complete"


async def test_turn_stream_debate_mode_persists_turns(app_client, auth_header):
    sid = await _open_session(app_client, auth_header)
    r = await app_client.post(
        f"/api/v1/sessions/{sid}/turns",
        headers=auth_header,
        json={"text": "Should we ship?", "language": "en", "mode": "debate"},
    )
    assert r.status_code == 200
    events = list(_parse_sse(r.text))
    agent_dones = [d for k, d in events if k == "agent_done"]
    # 5 specialists expected
    assert len(agent_dones) >= 5
    consensus = [d for k, d in events if k == "consensus"][0]
    assert consensus["kind"] in {"unanimous", "majority", "split"}

    # Verify turns persisted
    r2 = await app_client.get(f"/api/v1/sessions/{sid}/turns", headers=auth_header)
    assert r2.status_code == 200
    items = r2.json()["items"]
    # 1 user + at least 5 agent turns
    assert len(items) >= 6


async def test_turn_stream_session_not_found(app_client, auth_header):
    r = await app_client.post(
        "/api/v1/sessions/nonexistent/turns",
        headers=auth_header,
        json={"text": "hi"},
    )
    assert r.status_code == 404


async def test_turn_stream_on_closed_session_returns_409(app_client, auth_header):
    sid = await _open_session(app_client, auth_header)
    await app_client.post(f"/api/v1/sessions/{sid}/close", headers=auth_header)
    r = await app_client.post(
        f"/api/v1/sessions/{sid}/turns", headers=auth_header, json={"text": "x"}
    )
    assert r.status_code == 409


async def test_turn_stream_requires_auth(app_client):
    r = await app_client.post("/api/v1/sessions/x/turns", json={"text": "?"})
    assert r.status_code == 401


async def test_turn_stream_validation_empty_text(app_client, auth_header):
    sid = await _open_session(app_client, auth_header)
    r = await app_client.post(
        f"/api/v1/sessions/{sid}/turns", headers=auth_header, json={"text": ""}
    )
    assert r.status_code in (422, 400)
