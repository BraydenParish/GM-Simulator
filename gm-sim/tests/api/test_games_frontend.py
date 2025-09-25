from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.db import get_db
from app.main import app
from app.models import Base, Game, Team


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
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_list_games_by_week_returns_narratives(
    client: AsyncClient, test_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    async with test_sessionmaker() as session:
        home = Team(name="Home Squad", abbr="HOM")
        away = Team(name="Road Crew", abbr="ROD")
        session.add_all([home, away])
        await session.flush()

        game = Game(
            season=2025,
            week=1,
            home_team_id=home.id,
            away_team_id=away.id,
            home_score=24,
            away_score=21,
            box_json={},
            injuries_json=None,
            narrative_recap="Late heroics seal the win.",
            narrative_facts={"mvp": "QB1"},
        )
        session.add(game)
        await session.commit()

    response = await client.get("/games/by-week", params={"season": 2025, "week": 1})
    assert response.status_code == 200

    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) == 1
    recap = payload[0]
    assert recap["home_team_id"] == 1
    assert recap["away_team_id"] == 2
    assert recap["narrative_recap"] == "Late heroics seal the win."
    assert recap["narrative_facts"] == {"mvp": "QB1"}

    # Teams endpoint should surface seeded teams for UI lookups
    teams_response = await client.get("/teams/")
    assert teams_response.status_code == 200
    team_payload = teams_response.json()
    assert {team["abbr"] for team in team_payload} == {"HOM", "ROD"}
