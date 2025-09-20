from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.db import get_db
from app.main import app
from app.models import Base, Player, PracticeSquad, Team
from app.services.roster_rules import OL_POSITIONS


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


def _build_roster_positions() -> list[str]:
    ol_positions = sorted(OL_POSITIONS)
    remaining_positions = [
        "QB",
        "RB",
        "WR",
        "WR",
        "TE",
        "FB",
        "DE",
        "DT",
        "LB",
        "CB",
        "S",
        "DL",
    ]
    positions: list[str] = []
    positions.extend(ol_positions[:8])
    idx = 0
    while len(positions) < 53:
        positions.append(remaining_positions[idx % len(remaining_positions)])
        idx += 1
    return positions[:53]


@pytest_asyncio.fixture
async def roster_setup(
    test_sessionmaker: async_sessionmaker[AsyncSession],
) -> dict[str, Any]:
    async with test_sessionmaker() as session:
        team = Team(name="Roster Team", abbr="RST")
        session.add(team)
        await session.flush()

        roster_positions = _build_roster_positions()
        roster_players: list[Player] = []
        ol_ids: list[int] = []
        for idx, pos in enumerate(roster_positions, start=1):
            player = Player(name=f"Roster {idx}", pos=pos, team_id=team.id)
            session.add(player)
            roster_players.append(player)
        await session.flush()

        for player in roster_players:
            if (player.pos or "").upper() in OL_POSITIONS:
                ol_ids.append(player.id)

        practice_players: list[Player] = []
        for idx in range(20):
            ps_player = Player(name=f"Practice {idx}", pos="WR", team_id=team.id)
            session.add(ps_player)
            practice_players.append(ps_player)
        await session.commit()

        return {
            "team_id": team.id,
            "roster_ids": [player.id for player in roster_players],
            "practice_ids": [player.id for player in practice_players],
            "ol_ids": ol_ids,
        }


@pytest_asyncio.fixture
async def client(
    test_sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_practice_squad_assignment_limits(
    client: AsyncClient, roster_setup: dict[str, Any]
) -> None:
    team_id = roster_setup["team_id"]
    practice_ids = roster_setup["practice_ids"]

    for player_id in practice_ids[:16]:
        response = await client.post(
            "/roster/practice-squad/assign",
            json={
                "team_id": team_id,
                "player_id": player_id,
                "international_pathway": False,
                "ps_ir": False,
            },
        )
        assert response.status_code == 200

    response = await client.post(
        "/roster/practice-squad/assign",
        json={
            "team_id": team_id,
            "player_id": practice_ids[16],
            "international_pathway": False,
            "ps_ir": False,
        },
    )
    assert response.status_code == 422

    response = await client.post(
        "/roster/practice-squad/assign",
        json={
            "team_id": team_id,
            "player_id": practice_ids[16],
            "international_pathway": True,
            "ps_ir": False,
        },
    )
    assert response.status_code == 200

    response = await client.post(
        "/roster/practice-squad/assign",
        json={
            "team_id": team_id,
            "player_id": practice_ids[17],
            "international_pathway": True,
            "ps_ir": False,
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_gameday_actives_rules_and_elevations(
    client: AsyncClient,
    roster_setup: dict[str, Any],
    test_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    team_id = roster_setup["team_id"]
    roster_ids = roster_setup["roster_ids"]
    ol_ids = roster_setup["ol_ids"]
    practice_ids = roster_setup["practice_ids"]

    non_ol_ids = [player_id for player_id in roster_ids if player_id not in ol_ids]

    actives_bad = ol_ids[:7] + non_ol_ids[:41]
    inactives_bad = [player_id for player_id in roster_ids if player_id not in actives_bad][:5]

    response = await client.post(
        "/roster/gameday/set-actives",
        json={
            "team_id": team_id,
            "game_id": 1,
            "actives": actives_bad,
            "inactives": inactives_bad,
            "elevated_player_ids": [],
        },
    )
    assert response.status_code == 422

    assigned_entries: list[int] = []
    for player_id in practice_ids[:2]:
        resp = await client.post(
            "/roster/practice-squad/assign",
            json={
                "team_id": team_id,
                "player_id": player_id,
                "international_pathway": False,
                "ps_ir": False,
            },
        )
        assert resp.status_code == 200
        assigned_entries.append(resp.json()["id"])

    base_actives = ol_ids[:8] + non_ol_ids[:38]
    actives_good = base_actives + practice_ids[:2]
    inactives_good = [player_id for player_id in roster_ids if player_id not in base_actives][:7]

    response = await client.post(
        "/roster/gameday/set-actives",
        json={
            "team_id": team_id,
            "game_id": 2,
            "actives": actives_good,
            "inactives": inactives_good,
            "elevated_player_ids": practice_ids[:2],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ol_count"] >= 8

    async with test_sessionmaker() as session:
        entries = (
            (
                await session.execute(
                    select(PracticeSquad).where(PracticeSquad.id.in_(assigned_entries))
                )
            )
            .scalars()
            .all()
        )
        assert all(entry.elevations == 1 for entry in entries)


@pytest.mark.asyncio
async def test_elevation_limits_enforced(
    client: AsyncClient,
    roster_setup: dict[str, Any],
    test_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    team_id = roster_setup["team_id"]
    roster_ids = roster_setup["roster_ids"]
    ol_ids = roster_setup["ol_ids"]
    practice_ids = roster_setup["practice_ids"]

    # Assign three practice-squad players
    elevation_ids: list[int] = []
    for player_id in practice_ids[:3]:
        resp = await client.post(
            "/roster/practice-squad/assign",
            json={
                "team_id": team_id,
                "player_id": player_id,
                "international_pathway": False,
                "ps_ir": False,
            },
        )
        assert resp.status_code == 200
        elevation_ids.append(resp.json()["id"])

    base_for_three = ol_ids[:8] + [pid for pid in roster_ids if pid not in ol_ids][:37]
    inactives_three = [pid for pid in roster_ids if pid not in base_for_three][:8]

    response = await client.post(
        "/roster/gameday/set-actives",
        json={
            "team_id": team_id,
            "game_id": 3,
            "actives": base_for_three + practice_ids[:3],
            "inactives": inactives_three,
            "elevated_player_ids": practice_ids[:3],
        },
    )
    assert response.status_code == 422

    # Pre-set one player to the elevation limit
    async with test_sessionmaker() as session:
        entry = await session.get(PracticeSquad, elevation_ids[0])
        assert entry is not None
        entry.elevations = 3
        await session.commit()

    base_for_two = ol_ids[:8] + [pid for pid in roster_ids if pid not in ol_ids][:38]
    inactives_two = [pid for pid in roster_ids if pid not in base_for_two][:7]

    response = await client.post(
        "/roster/gameday/set-actives",
        json={
            "team_id": team_id,
            "game_id": 4,
            "actives": base_for_two + practice_ids[:2],
            "inactives": inactives_two,
            "elevated_player_ids": practice_ids[:2],
        },
    )
    assert response.status_code == 422
