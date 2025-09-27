from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select

from app.db import get_db
from app.main import app
from app.models import Base, PlayoffGame, Standing, Team


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with Session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield Session
    finally:
        app.dependency_overrides.pop(get_db, None)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
async def client(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
async def seeded_season(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        teams = []
        for index in range(1, 9):
            team = Team(name=f"Team {index}", abbr=f"T{index}", elo=1500 + index * 10)
            teams.append(team)
        session.add_all(teams)
        await session.flush()

        standings = []
        for idx, team in enumerate(teams, start=1):
            standings.append(
                Standing(
                    season=2024,
                    team_id=team.id,
                    wins=12 - idx,
                    losses=5 + (idx // 3),
                    ties=0,
                    pf=400 - idx * 5,
                    pa=300 + idx * 3,
                )
            )
        session.add_all(standings)
        await session.commit()


@pytest.mark.asyncio
async def test_simulate_playoffs_endpoint(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    seeded_season: None,
) -> None:
    response = await client.post(
        "/playoffs/simulate",
        params={"season": 2024, "bracket_size": 4},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["season"] == 2024
    assert payload["bracket_size"] == 4
    assert len(payload["games"]) == 3
    assert 1 <= payload["champion"]["seed"] <= 4

    async with session_factory() as session:
        stored_games = (
            await session.execute(select(PlayoffGame).where(PlayoffGame.season == 2024))
        ).scalars().all()
        assert len(stored_games) == 3
        assert all(game.round_name in {"Semifinals", "Championship"} for game in stored_games)
