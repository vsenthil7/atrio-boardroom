"""Memory service — per-tenant, per-agent persistent memory.

In production this uses pgvector with cosine similarity. In tests/SQLite we
compute cosine similarity in Python over the JSON-stored embeddings, which is
fine for the small datasets we use in tests.

The embedding function is pluggable; the default is a deterministic hash-
based pseudo-embedding so tests don't need an external embedding service.
"""
from __future__ import annotations

import hashlib
import math
from datetime import datetime
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import AgentMemory

log = get_logger(__name__)

EMBEDDING_DIMS = 64  # deliberately small for test speed
DEFAULT_RETRIEVAL_LIMIT = 5
DEFAULT_MIN_SIMILARITY = 0.10


# ---------------------------------------------------------------------------
# Embedding (pluggable)
# ---------------------------------------------------------------------------


def deterministic_embedding(text: str, dims: int = EMBEDDING_DIMS) -> list[float]:
    """Hash the text into a dim-sized float vector. Deterministic and free."""
    if not text:
        return [0.0] * dims
    # Build vector by hashing successive shifted seeds.
    vec: list[float] = []
    for i in range(dims):
        h = hashlib.sha256(f"{i}|{text}".encode()).digest()
        # convert first 4 bytes to int → fraction in [-1, 1]
        n = int.from_bytes(h[:4], "big", signed=False)
        vec.append(((n / 0xFFFFFFFF) * 2.0) - 1.0)
    return _l2_normalize(vec)


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm > 0 else vec


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ---------------------------------------------------------------------------
# MemoryService
# ---------------------------------------------------------------------------


class MemoryService:
    """Reads + writes per-agent persistent memory."""

    def __init__(
        self,
        session: AsyncSession,
        embed_fn: callable | None = None,
    ) -> None:
        self._session = session
        self._embed = embed_fn or deterministic_embedding

    # ----------------------------- writes

    async def write(
        self,
        *,
        tenant_id: str,
        agent_id: str,
        content: str,
        kind: str,
        weight: float = 1.0,
        source_session_id: str | None = None,
    ) -> AgentMemory:
        if kind not in ("session_summary", "salient_fact", "dissent_point", "seeded"):
            raise ValueError(f"invalid memory kind: {kind}")
        embedding = self._embed(content)
        mem = AgentMemory(
            tenant_id=tenant_id,
            agent_id=agent_id,
            source_session_id=source_session_id,
            kind=kind,
            content=content,
            embedding=list(embedding),
            weight=Decimal(str(weight)),
        )
        self._session.add(mem)
        await self._session.flush()
        return mem

    async def write_session_summary(
        self,
        *,
        tenant_id: str,
        agent_id: str,
        source_session_id: str,
        summary: str,
        salient_facts: Iterable[str] = (),
        dissent_points: Iterable[str] = (),
    ) -> list[AgentMemory]:
        out: list[AgentMemory] = []
        out.append(
            await self.write(
                tenant_id=tenant_id,
                agent_id=agent_id,
                content=summary,
                kind="session_summary",
                weight=1.0,
                source_session_id=source_session_id,
            )
        )
        for fact in salient_facts:
            out.append(
                await self.write(
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    content=fact,
                    kind="salient_fact",
                    weight=2.0,
                    source_session_id=source_session_id,
                )
            )
        for dissent in dissent_points:
            out.append(
                await self.write(
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    content=dissent,
                    kind="dissent_point",
                    weight=1.5,
                    source_session_id=source_session_id,
                )
            )
        return out

    # ----------------------------- reads

    async def retrieve(
        self,
        *,
        tenant_id: str,
        agent_id: str,
        query: str,
        limit: int = DEFAULT_RETRIEVAL_LIMIT,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
    ) -> list[tuple[AgentMemory, float]]:
        q_embed = self._embed(query)
        stmt = (
            select(AgentMemory)
            .where(
                AgentMemory.tenant_id == tenant_id,
                AgentMemory.agent_id == agent_id,
                AgentMemory.deleted_at.is_(None),
            )
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        scored: list[tuple[AgentMemory, float]] = []
        for mem in rows:
            sim = cosine(q_embed, list(mem.embedding))
            weighted = sim * float(mem.weight)
            if weighted >= min_similarity:
                scored.append((mem, weighted))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        top = scored[:limit]
        # Update retrieval_count + last_retrieved_at
        for mem, _ in top:
            await self._session.execute(
                update(AgentMemory)
                .where(AgentMemory.id == mem.id)
                .values(
                    retrieval_count=AgentMemory.retrieval_count + 1,
                    last_retrieved_at=datetime.utcnow(),
                )
            )
        await self._session.flush()
        return top

    async def list_for_agent(
        self, *, tenant_id: str, agent_id: str, limit: int = 100
    ) -> list[AgentMemory]:
        stmt = (
            select(AgentMemory)
            .where(
                AgentMemory.tenant_id == tenant_id,
                AgentMemory.agent_id == agent_id,
                AgentMemory.deleted_at.is_(None),
            )
            .order_by(AgentMemory.ts.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows)

    async def soft_delete_for_tenant(self, *, tenant_id: str) -> int:
        """GDPR erasure helper. Returns rows affected."""
        result = await self._session.execute(
            update(AgentMemory)
            .where(AgentMemory.tenant_id == tenant_id, AgentMemory.deleted_at.is_(None))
            .values(deleted_at=datetime.utcnow())
        )
        await self._session.flush()
        return int(result.rowcount or 0)
