"""Voice router — issue LiveKit join tokens.

POST /voice/sessions/{session_id}/join → { livekit_url, room, token, identity }
GET  /voice/config                     → STT supported langs + custom dictionary

The full LiveKit + Speechmatics pipeline runs in a sidecar; the API surface
here is small. We mint a short-lived LiveKit access JWT bound to the user
and the session room.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbSession
from app.api.schemas import LiveKitJoinResponse
from app.audit.service import AuditService
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.db.models import Session as SessionRow
from app.voice.service import VoiceService
from app.voice.speechmatics import SUPPORTED_LANGUAGES, load_custom_dictionary

router = APIRouter(prefix="/voice", tags=["voice"])


@router.get("/config")
async def voice_config(user: CurrentUserDep) -> dict[str, object]:
    """Public voice config for the frontend."""
    s = get_settings()
    from app.core.config import project_root

    dict_path = Path(s.dictionaries_dir)
    if not dict_path.is_absolute():
        dict_path = project_root() / dict_path
    dict_path = dict_path / "demo_en.txt"
    terms = load_custom_dictionary(dict_path)
    return {
        "supported_languages": list(SUPPORTED_LANGUAGES),
        "default_language": "en",
        "custom_dictionary_size": len(terms),
        "tenant_id": user.tenant_id,
    }



@router.post("/sessions/{session_id}/join", response_model=LiveKitJoinResponse)
async def join_session(
    session_id: str, user: CurrentUserDep, db: DbSession
) -> LiveKitJoinResponse:
    sess = (
        await db.execute(
            select(SessionRow).where(
                SessionRow.id == session_id, SessionRow.tenant_id == user.tenant_id
            )
        )
    ).scalar_one_or_none()
    if sess is None:
        raise NotFoundError("session not found", details={"session_id": session_id})

    svc = VoiceService()
    join = svc.issue_join_token(
        tenant_id=user.tenant_id,
        session_id=session_id,
        user_id=user.user_id,
        display_name=user.display_name,
    )
    await AuditService(db).write(
        tenant_id=user.tenant_id,
        session_id=session_id,
        actor_user_id=user.user_id,
        kind="voice_session_joined",
        payload={"room": join.room, "identity": join.identity},
    )
    return LiveKitJoinResponse(
        livekit_url=join.livekit_url,
        room=join.room,
        token=join.token,
        identity=join.identity,
    )
