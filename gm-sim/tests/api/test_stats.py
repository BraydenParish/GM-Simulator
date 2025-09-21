import os
import sys
import tempfile
from pathlib import Path
from typing import Dict

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy import select

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.db import get_db
from app.main import app
from app.models import Base, Player, PlayerSeasonStat, Team, TeamSeasonStat


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
                Player(id=105, name="Terry Tight", pos="TE", team_id=1, ovr=83),
                Player(id=106, name="Benny Burst", pos="RB", team_id=1, ovr=79),
                Player(id=107, name="Slot Sam", pos="WR", team_id=1, ovr=81),
                Player(id=108, name="Line Leo", pos="LB", team_id=1, ovr=77),
                Player(id=201, name="Quinn Quick", pos="QB", team_id=2, ovr=89),
                Player(id=202, name="Baker Burst", pos="RB", team_id=2, ovr=83),
                Player(id=203, name="Cal Catch", pos="WR", team_id=2, ovr=87),
                Player(id=204, name="Dax Drive", pos="DE", team_id=2, ovr=81),
                Player(id=205, name="Tanner Tight", pos="TE", team_id=2, ovr=84),
                Player(id=206, name="Ricky Relief", pos="RB", team_id=2, ovr=78),
                Player(id=207, name="Zed Zoom", pos="WR", team_id=2, ovr=82),
                Player(id=208, name="Mike Mike", pos="LB", team_id=2, ovr=76),
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


def _totals_by_team(*games_payloads):
    totals: Dict[int, Dict[str, int]] = {}
    for payload in games_payloads:
        for entry in payload["box_json"]["player_stats"]:
            team_totals = totals.setdefault(entry["team_id"], {})
            for key, value in entry["stats"].items():
                team_totals[key] = team_totals.get(key, 0) + value
    return totals


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
async def test_simulation_spreads_stats_across_depth_chart(client: AsyncClient):
    response = await client.post(
        "/games/simulate",
        params={
            "home_team_id": 1,
            "away_team_id": 2,
            "season": 2027,
            "week": 2,
            "sim_seed": 11,
        },
    )
    assert response.status_code == 200
    stats_payload = response.json()["box_json"]["player_stats"]

    players_by_team: Dict[int, set[int]] = {1: set(), 2: set()}
    for entry in stats_payload:
        players_by_team.setdefault(entry["team_id"], set()).add(entry["player_id"])

    assert len(players_by_team[1]) >= 4
    assert len(players_by_team[2]) >= 4


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


@pytest.mark.asyncio
async def test_team_season_stats_aggregate(client: AsyncClient, test_db):
    first = await client.post(
        "/games/simulate",
        params={
            "home_team_id": 1,
            "away_team_id": 2,
            "season": 2028,
            "week": 1,
            "sim_seed": 31,
        },
    )
    second = await client.post(
        "/games/simulate",
        params={
            "home_team_id": 2,
            "away_team_id": 1,
            "season": 2028,
            "week": 2,
            "sim_seed": 32,
        },
    )
    assert first.status_code == 200
    assert second.status_code == 200

    totals = _totals_by_team(first.json(), second.json())

    response = await client.get("/stats/teams/season", params={"season": 2028})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == len(totals)
    for entry in payload:
        expected = totals[entry["team_id"]]
        assert entry["games_played"] == 2
        assert entry["stats"] == expected

    filtered = await client.get(
        "/stats/teams/season", params={"season": 2028, "team_id": 1}
    )
    assert filtered.status_code == 200
    filtered_payload = filtered.json()
    assert len(filtered_payload) == 1
    assert filtered_payload[0]["team_id"] == 1
    assert filtered_payload[0]["stats"] == totals[1]

    async with test_db() as session:
        record = (
            await session.execute(
                select(TeamSeasonStat).where(
                    TeamSeasonStat.season == 2028,
                    TeamSeasonStat.team_id == 1,
                )
            )
        ).scalar_one()
        assert record.games_played == 2
