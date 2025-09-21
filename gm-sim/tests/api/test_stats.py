import os
import sys
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy import select

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.db import get_db
from app.main import app
from app.models import Base, Player, PlayerSeasonStat, Team


@pytest.fixture
async def test_db():
    fd, path = tempfile.mkstemp(prefix="stats-test-", suffix=".db")
    os.close(fd)
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path}", future=True, poolclass=NullPool
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        session.add_all(
            [
                Team(id=1, name="Alpha", abbr="ALP"),
                Team(id=2, name="Beta", abbr="BET"),
            ]
        )
        session.add_all(
            [
                Player(id=101, name="Allen Arm", pos="QB", team_id=1, ovr=92),
                Player(id=102, name="Riley Rush", pos="RB", team_id=1, ovr=85),
                Player(id=103, name="Will Wing", pos="WR", team_id=1, ovr=88),
                Player(id=104, name="Edge Enzo", pos="EDGE", team_id=1, ovr=80),
                Player(id=201, name="Quinn Quick", pos="QB", team_id=2, ovr=89),
                Player(id=202, name="Baker Burst", pos="RB", team_id=2, ovr=83),
                Player(id=203, name="Cal Catch", pos="WR", team_id=2, ovr=87),
                Player(id=204, name="Dax Drive", pos="DE", team_id=2, ovr=81),
            ]
        )
        await session.commit()

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield session_factory
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


@pytest.fixture
async def client(test_db):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as test_client:
        yield test_client


def _stats_by_player(stats_payload):
    return {
        (entry["player_id"], entry["team_id"]): entry["stats"]
        for entry in stats_payload
    }


@pytest.mark.asyncio
async def test_simulation_creates_player_stats(client: AsyncClient):
    response = await client.post(
        "/games/simulate",
        params={
            "home_team_id": 1,
            "away_team_id": 2,
            "season": 2027,
            "week": 1,
            "sim_seed": 7,
        },
    )
    assert response.status_code == 200
    game_payload = response.json()
    assert game_payload["box_json"]["player_stats"]

    game_stats_response = await client.get(
        "/stats/players/game", params={"game_id": game_payload["id"]}
    )
    assert game_stats_response.status_code == 200
    stored_stats = game_stats_response.json()
    assert len(stored_stats) == len(game_payload["box_json"]["player_stats"])

    indexed_sim = _stats_by_player(game_payload["box_json"]["player_stats"])
    indexed_db = _stats_by_player(stored_stats)
    assert indexed_sim.keys() == indexed_db.keys()
    for key in indexed_sim:
        assert indexed_sim[key] == indexed_db[key]

    alpha_only = await client.get(
        "/stats/players/game", params={"game_id": game_payload["id"], "team_id": 1}
    )
    assert all(entry["team_id"] == 1 for entry in alpha_only.json())


@pytest.mark.asyncio
async def test_season_stats_accumulate(client: AsyncClient, test_db):
    first = await client.post(
        "/games/simulate",
        params={
            "home_team_id": 1,
            "away_team_id": 2,
            "season": 2027,
            "week": 1,
            "sim_seed": 21,
        },
    )
    assert first.status_code == 200
    first_payload = first.json()

    second = await client.post(
        "/games/simulate",
        params={
            "home_team_id": 1,
            "away_team_id": 2,
            "season": 2027,
            "week": 2,
            "sim_seed": 22,
        },
    )
    assert second.status_code == 200
    second_payload = second.json()

    first_stats = _stats_by_player(first_payload["box_json"]["player_stats"])
    second_stats = _stats_by_player(second_payload["box_json"]["player_stats"])

    season_response = await client.get(
        "/stats/players/season", params={"season": 2027, "player_id": 101}
    )
    assert season_response.status_code == 200
    player_totals = season_response.json()
    assert len(player_totals) == 1
    totals_entry = player_totals[0]
    assert totals_entry["games_played"] == 2

    expected_totals = {
        key: first_stats[(101, 1)][key] + second_stats[(101, 1)][key]
        for key in first_stats[(101, 1)]
    }
    assert totals_entry["stats"] == expected_totals

    alpha_team_totals = await client.get(
        "/stats/players/season", params={"season": 2027, "team_id": 1}
    )
    assert alpha_team_totals.status_code == 200
    assert all(entry["team_id"] == 1 for entry in alpha_team_totals.json())

    async with test_db() as session:
        season_records = (
            await session.execute(
                select(PlayerSeasonStat).where(
                    PlayerSeasonStat.season == 2027,
                    PlayerSeasonStat.player_id == 101,
                )
            )
        ).scalar_one()
        assert season_records.games_played == 2
