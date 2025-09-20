from collections.abc import AsyncIterator
from pathlib import Path
import sys
from typing import List

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.db import get_db
from app.main import app
from app.models import Base, Injury, Player, PlayerStamina, Team
from app.services.injuries import InjuryEvent, PlayerParticipation


class StubInjuryEngine:
    def simulate_game(
        self, team_id: int, participants: List[PlayerParticipation]
    ) -> List[InjuryEvent]:
        events: List[InjuryEvent] = []
        for index, participant in enumerate(participants, start=1):
            participant.fatigue += 12.0
            if index == 1:
                events.append(
                    InjuryEvent(
                        player_id=participant.player_id,
                        team_id=team_id,
                        severity="moderate",
                        weeks_out=3,
                        occurred_snap=10,
                        injury_type="Test Injury",
                    )
                )
        return events


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


@pytest_asyncio.fixture
async def seed_game_data(
    test_sessionmaker: async_sessionmaker[AsyncSession],
) -> List[int]:
    async with test_sessionmaker() as session:
        home = Team(name="Home Team", abbr="HOM")
        away = Team(name="Road Team", abbr="AWY")
        session.add_all([home, away])
        await session.flush()

        session.add_all(
            [
                Player(name="Home QB", pos="QB", team_id=home.id),
                Player(name="Home RB", pos="RB", team_id=home.id),
                Player(name="Away QB", pos="QB", team_id=away.id),
            ]
        )

        await session.commit()
        return [home.id, away.id]


@pytest.mark.asyncio
async def test_simulate_game_persists_injuries_and_fatigue(
    client: AsyncClient,
    seed_game_data: List[int],
    monkeypatch: pytest.MonkeyPatch,
    test_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    from app import routers

    monkeypatch.setattr(routers.games, "InjuryEngine", lambda: StubInjuryEngine())

    response = await client.post(
        "/games/simulate",
        params={
            "home_team_id": seed_game_data[0],
            "away_team_id": seed_game_data[1],
            "season": 2025,
            "week": 1,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["injuries_json"]

    async with test_sessionmaker() as session:
        injuries = (await session.execute(select(Injury))).scalars().all()
        assert injuries
        stored = injuries[0]
        assert stored.type == "Test Injury"
        assert stored.expected_weeks_out == 3

        stamina_rows = (
            (await session.execute(select(PlayerStamina).order_by(PlayerStamina.player_id)))
            .scalars()
            .all()
        )
        assert stamina_rows
        assert any(row.fatigue >= 12.0 for row in stamina_rows)
