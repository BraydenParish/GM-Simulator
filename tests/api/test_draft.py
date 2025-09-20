from __future__ import annotations

import sys
from pathlib import Path
from collections import Counter
from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.db import get_db
from app.main import app
from app.models import Base, Player


@pytest_asyncio.fixture
async def test_sessionmaker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield session_factory
    finally:
        app.dependency_overrides.pop(get_db, None)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture
async def client(
    test_sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_generate_draft_class_creates_rookies(
    client: AsyncClient,
    test_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    payload = {"year": 2025, "rounds": 2, "players_per_round": 4, "seed": 7}

    response = await client.post("/draft/generate-class", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["year"] == 2025
    assert data["total"] == 8
    assert all(player["team_id"] is None for player in data["items"])
    assert all(player["rookie_year"] == 2025 for player in data["items"])

    async with test_sessionmaker() as session:
        result = await session.execute(select(Player))
        players = list(result.scalars())
        assert len(players) == 8
        assert len({player.name for player in players}) == 8


@pytest.mark.asyncio
async def test_generate_draft_class_blocks_duplicate_year(
    client: AsyncClient,
) -> None:
    payload = {"year": 2026, "rounds": 1, "players_per_round": 2, "seed": 3}

    first = await client.post("/draft/generate-class", json=payload)
    assert first.status_code == 201

    duplicate = await client.post("/draft/generate-class", json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "draft class already generated for this year"


@pytest.mark.asyncio
async def test_generate_draft_class_respects_custom_weights(
    client: AsyncClient,
    test_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    payload = {
        "year": 2027,
        "rounds": 1,
        "players_per_round": 8,
        "seed": 11,
        "position_weights": {"QB": 3, "K": 1},
    }

    response = await client.post("/draft/generate-class", json=payload)
    assert response.status_code == 201
    data = response.json()
    positions = Counter(player["pos"] for player in data["items"])
    assert set(positions) <= {"QB", "K"}
    # Weighted randomness with the supplied seed yields four quarterbacks and four kickers
    assert positions["QB"] == 4
    assert positions["K"] == 4
