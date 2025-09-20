from collections.abc import AsyncIterator
from pathlib import Path
import sys
from typing import List

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.db import get_db
from app.main import app
from app.models import Base, Game, Injury, Player, PlayerStamina, Team


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
async def seed_health_data(
    test_sessionmaker: async_sessionmaker[AsyncSession],
) -> List[int]:
    async with test_sessionmaker() as session:
        team_a = Team(name="Metro Stars", abbr="MET")
        team_b = Team(name="Coastal Kings", abbr="CST")
        session.add_all([team_a, team_b])
        await session.flush()

        players = [
            Player(name="Alex Runner", pos="RB", team_id=team_a.id),
            Player(name="Blake Thrower", pos="QB", team_id=team_a.id),
            Player(name="Chris Catcher", pos="WR", team_id=team_b.id),
        ]
        session.add_all(players)
        await session.flush()

        game = Game(
            season=2024,
            week=1,
            home_team_id=team_a.id,
            away_team_id=team_b.id,
            home_score=24,
            away_score=17,
            sim_seed=42,
            box_json={},
            injuries_json=[],
        )
        session.add(game)
        await session.flush()

        session.add_all(
            [
                Injury(
                    player_id=players[0].id,
                    team_id=team_a.id,
                    game_id=game.id,
                    type="Hamstring pull",
                    severity="moderate",
                    expected_weeks_out=3,
                    occurred_at_play_id=12,
                ),
                Injury(
                    player_id=players[1].id,
                    team_id=team_a.id,
                    game_id=game.id,
                    type="Shoulder sprain",
                    severity="major",
                    expected_weeks_out=6,
                    occurred_at_play_id=28,
                ),
                Injury(
                    player_id=players[2].id,
                    team_id=team_b.id,
                    game_id=game.id,
                    type="Ankle tweak",
                    severity="minor",
                    expected_weeks_out=0,
                    occurred_at_play_id=8,
                ),
            ]
        )

        session.add_all(
            [
                PlayerStamina(player_id=players[0].id, fatigue=72.0),
                PlayerStamina(player_id=players[1].id, fatigue=48.0),
                PlayerStamina(player_id=players[2].id, fatigue=64.0),
            ]
        )

        await session.commit()

        return [team_a.id, team_b.id]


@pytest_asyncio.fixture
async def client(
    test_sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_list_injuries_filters(client: AsyncClient, seed_health_data: List[int]) -> None:
    response = await client.get("/health/injuries")
    assert response.status_code == 200
    payload = response.json()

    # Only two active injuries (expected_weeks_out > 0)
    assert payload["total"] == 2
    player_names = {item["player_name"] for item in payload["items"]}
    assert player_names == {"Alex Runner", "Blake Thrower"}

    response = await client.get(
        "/health/injuries",
        params={"team_id": seed_health_data[0], "severity": "major"},
    )
    assert response.status_code == 200
    filtered = response.json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["player_name"] == "Blake Thrower"

    response = await client.get("/health/injuries", params={"active_only": False})
    assert response.status_code == 200
    all_injuries = response.json()
    assert all_injuries["total"] == 3


@pytest.mark.asyncio
async def test_team_health_summary(client: AsyncClient, seed_health_data: List[int]) -> None:
    response = await client.get("/health/summary")
    assert response.status_code == 200
    payload = response.json()

    items = payload["items"]
    assert len(items) == 2
    metro = next(item for item in items if item["team_name"] == "Metro Stars")
    coastal = next(item for item in items if item["team_name"] == "Coastal Kings")

    assert metro["active_injuries"] == 2
    assert metro["severe_injuries"] == 1
    assert metro["high_fatigue_players"] == 1
    assert metro["average_fatigue"] >= 60.0

    assert coastal["active_injuries"] == 0
    assert coastal["high_fatigue_players"] == 1
