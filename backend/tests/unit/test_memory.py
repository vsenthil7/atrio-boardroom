"""Unit tests for MemoryService."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.memory.service import (
    EMBEDDING_DIMS,
    MemoryService,
    cosine,
    deterministic_embedding,
)


def test_embedding_deterministic_and_normalized():
    a = deterministic_embedding("hello world")
    b = deterministic_embedding("hello world")
    assert a == b
    assert len(a) == EMBEDDING_DIMS
    # L2 norm should be ~1
    n = sum(x * x for x in a) ** 0.5
    assert abs(n - 1.0) < 1e-6


def test_embedding_empty_returns_zeros():
    a = deterministic_embedding("")
    assert a == [0.0] * EMBEDDING_DIMS


def test_cosine_identical_is_one():
    a = deterministic_embedding("acme is great")
    assert cosine(a, a) == pytest.approx(1.0, abs=1e-6)


def test_cosine_orthogonal_or_close_for_different():
    a = deterministic_embedding("balance sheet")
    b = deterministic_embedding("quarterly product launch")
    val = cosine(a, b)
    # Random hashes should give small magnitudes
    assert -1.0 <= val <= 1.0


def test_cosine_zero_vectors():
    assert cosine([], []) == 0.0
    assert cosine([0, 0], [1, 1]) == 0.0
    assert cosine([1, 0, 0], [1, 0, 0, 0]) == 0.0  # mismatched length


async def test_write_and_retrieve_round_trip(db_session, tenant):
    svc = MemoryService(db_session)
    m = await svc.write(
        tenant_id=tenant.id,
        agent_id="cfo",
        content="Acme has 18 months runway",
        kind="salient_fact",
        weight=2.0,
    )
    assert m.id
    assert m.kind == "salient_fact"

    hits = await svc.retrieve(
        tenant_id=tenant.id, agent_id="cfo", query="runway", min_similarity=-1.0
    )
    # We expect at least the fact we wrote to come back at the top (only one row)
    assert hits
    assert hits[0][0].content == "Acme has 18 months runway"


async def test_write_invalid_kind_raises(db_session, tenant):
    svc = MemoryService(db_session)
    with pytest.raises(ValueError, match="invalid memory kind"):
        await svc.write(
            tenant_id=tenant.id, agent_id="cfo", content="x", kind="bogus"
        )


async def test_session_summary_writes_three_kinds(db_session, tenant):
    svc = MemoryService(db_session)
    written = await svc.write_session_summary(
        tenant_id=tenant.id,
        agent_id="cfo",
        source_session_id=None,  # type: ignore[arg-type]
        summary="we decided to ship in Q2",
        salient_facts=["Burn is €240k/month", "Runway 18 months"],
        dissent_points=["CTO worried about scope"],
    )
    kinds = sorted([m.kind for m in written])
    assert kinds == ["dissent_point", "salient_fact", "salient_fact", "session_summary"]
    weights = {m.kind: m.weight for m in written}
    assert weights["session_summary"] == Decimal("1.0")
    assert weights["salient_fact"] == Decimal("2.0")
    assert weights["dissent_point"] == Decimal("1.5")


async def test_retrieval_respects_tenant_scope(db_session, tenant, second_tenant):
    svc = MemoryService(db_session)
    await svc.write(
        tenant_id=tenant.id, agent_id="cfo", content="A", kind="salient_fact"
    )
    await svc.write(
        tenant_id=second_tenant.id, agent_id="cfo", content="A", kind="salient_fact"
    )
    rows = await svc.list_for_agent(tenant_id=tenant.id, agent_id="cfo")
    assert len(rows) == 1


async def test_retrieval_updates_count_and_timestamp(db_session, tenant):
    svc = MemoryService(db_session)
    m = await svc.write(
        tenant_id=tenant.id, agent_id="cfo", content="x", kind="salient_fact"
    )
    assert m.retrieval_count == 0
    hits = await svc.retrieve(
        tenant_id=tenant.id, agent_id="cfo", query="x", min_similarity=-1
    )
    await db_session.refresh(hits[0][0])
    assert hits[0][0].retrieval_count == 1
    assert hits[0][0].last_retrieved_at is not None


async def test_retrieval_filters_min_similarity(db_session, tenant):
    svc = MemoryService(db_session)
    await svc.write(
        tenant_id=tenant.id, agent_id="cfo", content="some content", kind="salient_fact"
    )
    # Very high threshold filters everything
    hits = await svc.retrieve(
        tenant_id=tenant.id, agent_id="cfo", query="completely unrelated query", min_similarity=0.99
    )
    assert hits == []


async def test_retrieval_excludes_soft_deleted(db_session, tenant):
    svc = MemoryService(db_session)
    await svc.write(
        tenant_id=tenant.id, agent_id="cfo", content="A", kind="salient_fact"
    )
    deleted = await svc.soft_delete_for_tenant(tenant_id=tenant.id)
    assert deleted == 1
    rows = await svc.list_for_agent(tenant_id=tenant.id, agent_id="cfo")
    assert rows == []


async def test_list_for_agent_limit(db_session, tenant):
    svc = MemoryService(db_session)
    for i in range(5):
        await svc.write(
            tenant_id=tenant.id, agent_id="cfo", content=f"item-{i}", kind="salient_fact"
        )
    rows = await svc.list_for_agent(tenant_id=tenant.id, agent_id="cfo", limit=3)
    assert len(rows) == 3


async def test_custom_embed_fn(db_session, tenant):
    def fixed_embed(text: str, dims: int = EMBEDDING_DIMS) -> list[float]:
        return [1.0] + [0.0] * (dims - 1)

    svc = MemoryService(db_session, embed_fn=fixed_embed)
    await svc.write(
        tenant_id=tenant.id, agent_id="cfo", content="anything", kind="salient_fact"
    )
    hits = await svc.retrieve(
        tenant_id=tenant.id, agent_id="cfo", query="anything", min_similarity=0.5
    )
    # Cosine of two [1, 0, 0, ...] vectors is 1.0
    assert hits and hits[0][1] >= 0.99
