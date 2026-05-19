"""Voice service — LiveKit token + Speechmatics bridge stub.

Production wires this to LiveKit's go-jose-compatible token (HMAC SHA256 with
the API secret). The sidecar joins the same room as the user, opens a
Speechmatics realtime WS, and republishes interim transcripts.

In the hackathon scope here we only mint the join token; the sidecar runs
out of process. The bridge is described but not implemented to avoid
shipping an extra long-running process for the unit tests.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from jose import jwt

from app.core.config import get_settings


@dataclass(frozen=True)
class LiveKitJoin:
    livekit_url: str
    room: str
    token: str
    identity: str


class VoiceService:
    """Issue LiveKit join tokens and (in prod) coordinate the STT bridge."""

    def issue_join_token(
        self,
        *,
        tenant_id: str,
        session_id: str,
        user_id: str,
        display_name: str,
        ttl_seconds: int = 600,
    ) -> LiveKitJoin:
        settings = get_settings()
        room = f"atrio-{tenant_id[:8]}-{session_id[:8]}"
        identity = f"u-{user_id[:12]}-{uuid.uuid4().hex[:6]}"
        now = int(time.time())
        # LiveKit JWT claim shape
        claims = {
            "iss": settings.livekit_api_key,
            "sub": identity,
            "iat": now,
            "exp": now + ttl_seconds,
            "nbf": now,
            "name": display_name,
            "video": {
                "room": room,
                "roomJoin": True,
                "canPublish": True,
                "canSubscribe": True,
                "canPublishData": True,
            },
        }
        # HS256 with the API secret
        token = jwt.encode(claims, settings.livekit_api_secret, algorithm="HS256")
        return LiveKitJoin(
            livekit_url=settings.livekit_url,
            room=room,
            token=token,
            identity=identity,
        )
