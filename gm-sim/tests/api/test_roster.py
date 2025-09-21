import os
import sys
import tempfile
from pathlib import Path
from typing import Iterable, List

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.db import get_db
from app.main import app
from app.models import Base, Player, PracticeSquad, Team


OL_POSITIONS = ["LT", "LG", "C", "RG", "RT", "LG", "RG", "C"]


def build_roster(elevated: Iterable[int] | None = None) -> tuple[List[int], List[int]]:
    elevated_list = list(elevated or [])
    base_ids = list(range(1, 54))[: 53 - len(elevated_list)]
    total_ids = elevated_list + base_ids
    assert len(total_ids) == 53
    actives = total_ids[:48]
    inactives = total_ids[48:]
    return actives, inactives


@pytest.fixture
async def test_db():
    fd, path = tempfile.mkstemp(prefix="roster-test-", suffix=".db")
    os.close(fd)
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path}",
        future=True,
        poolclass=NullPool,
    )
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        session.add(Team(id=1, name="Alpha", abbr="ALP"))
        players: List[Player] = []
        for idx, pos in enumerate(OL_POSITIONS, start=1):
            players.append(Player(id=idx, name=f"OL {idx}", pos=pos, team_id=1))
        for idx in range(len(OL_POSITIONS) + 1, 54):
            pos = "WR" if idx % 3 == 0 else "CB"
            players.append(Player(id=idx, name=f"Player {idx}", pos=pos, team_id=1))
        practice_players = [
            Player(id=pid, name=f"Practice {pid}", pos="WR", team_id=None)
            for pid in list(range(200, 218)) + list(range(300, 305))
        ]
        session.add_all(players + practice_players)
        await session.commit()

    async def override_get_db():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield async_session
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


@pytest.mark.asyncio
async def test_practice_squad_capacity_and_ipp_slot(client: AsyncClient):
    for player_id in range(200, 216):
        response = await client.post(
            "/roster/practice-squad/assign",
            json={"team_id": 1, "player_id": player_id},
        )
        assert response.status_code == 200

    response = await client.post(
        "/roster/practice-squad/assign",
        json={"team_id": 1, "player_id": 216},
    )
    assert response.status_code == 422

    response = await client.post(
        "/roster/practice-squad/assign",
        json={"team_id": 1, "player_id": 216, "international_pathway": True},
    )
    assert response.status_code == 200

    response = await client.post(
        "/roster/practice-squad/assign",
        json={"team_id": 1, "player_id": 217, "international_pathway": True},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_gameday_actives_enforces_rules(client: AsyncClient):
    actives, inactives = build_roster()
    response = await client.post(
        "/roster/gameday/set-actives",
        json={
            "game_id": 1,
            "team_id": 1,
            "actives": actives,
            "inactives": inactives,
            "elevated_player_ids": [],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    assert payload["ol_count"] == 8

    bad_actives = actives.copy()
    bad_inactives = inactives.copy()
    removed_ol = next(pid for pid in bad_actives if pid <= len(OL_POSITIONS))
    bad_actives.remove(removed_ol)
    replacement = bad_inactives.pop()
    bad_actives.append(replacement)
    bad_inactives.append(removed_ol)

    response = await client.post(
        "/roster/gameday/set-actives",
        json={
            "game_id": 2,
            "team_id": 1,
            "actives": bad_actives,
            "inactives": bad_inactives,
            "elevated_player_ids": [],
        },
    )
    assert response.status_code == 422

    short_actives = actives[:-1]
    extra_inactives = inactives + [actives[-1]]
    response = await client.post(
        "/roster/gameday/set-actives",
        json={
            "game_id": 3,
            "team_id": 1,
            "actives": short_actives,
            "inactives": extra_inactives,
            "elevated_player_ids": [],
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_practice_squad_elevation_limits(client: AsyncClient, test_db):
    for player_id in (300, 301, 302):
        response = await client.post(
            "/roster/practice-squad/assign",
            json={"team_id": 1, "player_id": player_id},
        )
        assert response.status_code == 200

    actives, inactives = build_roster(elevated=[300, 301, 302])
    response = await client.post(
        "/roster/gameday/set-actives",
        json={
            "game_id": 10,
            "team_id": 1,
            "actives": actives,
            "inactives": inactives,
            "elevated_player_ids": [300, 301, 302],
        },
    )
    assert response.status_code == 422

    async with test_db() as session:
        entry = (
            await session.execute(
                select(PracticeSquad).where(PracticeSquad.player_id == 300)
            )
        ).scalar_one()
        entry.elevations = 2
        await session.commit()

    actives, inactives = build_roster(elevated=[300, 301])
    response = await client.post(
        "/roster/gameday/set-actives",
        json={
            "game_id": 11,
            "team_id": 1,
            "actives": actives,
            "inactives": inactives,
            "elevated_player_ids": [300, 301],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["elevated_player_ids"] == [300, 301]

    async with test_db() as session:
        entry = (
            await session.execute(
                select(PracticeSquad).where(PracticeSquad.player_id == 300)
            )
        ).scalar_one()
        assert entry.elevations == 3

    actives, inactives = build_roster(elevated=[300])
    response = await client.post(
        "/roster/gameday/set-actives",
        json={
            "game_id": 12,
            "team_id": 1,
            "actives": actives,
            "inactives": inactives,
            "elevated_player_ids": [300],
        },
    )
    assert response.status_code == 422
