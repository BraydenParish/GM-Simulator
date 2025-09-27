from __future__ import annotations

from typing import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import get_db
from app.main import app
from app.models import Base, Team


@pytest.fixture
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


@pytest.fixture
async def client(
    test_sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


@pytest.mark.asyncio
async def test_coaching_lifecycle(client: AsyncClient, test_sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    coach_payload = {
        "name": "Helena Strategist",
        "role_primary": "HC",
        "scheme": "West Coast",
        "leadership": 4.5,
        "development": 3.8,
        "tactics": 4.1,
        "discipline": 2.5,
        "experience_years": 11,
        "specialties": ["QB", "WR"],
    }
    coach_response = await client.post("/coaching/coaches", json=coach_payload)
    assert coach_response.status_code == 201
    coach_id = coach_response.json()["id"]

    async with test_sessionmaker() as session:
        team = Team(name="Test Franchise", abbr="TFR", scheme_off="West Coast", scheme_def="Cover 2")
        session.add(team)
        await session.commit()
        team_id = team.id

    hire_payload = {
        "team_id": team_id,
        "role": "HC",
        "contract_years": 4,
        "salary": 4.0,
        "interim": False,
    }
    hire_response = await client.post(f"/coaching/coaches/{coach_id}/hire", json=hire_payload)
    assert hire_response.status_code == 200
    assignment = hire_response.json()
    assert assignment["coach_name"] == "Helena Strategist"
    assert assignment["team_id"] == team_id

    overview_response = await client.get(f"/coaching/teams/{team_id}")
    assert overview_response.status_code == 200
    overview = overview_response.json()
    assert overview["assignments"]
    assert overview["effect"]["rating_adjustment"] >= 0

    fire_response = await client.post(f"/coaching/coaches/{coach_id}/fire")
    assert fire_response.status_code == 200
    assert fire_response.json()["assignment_id"] == assignment["id"]
