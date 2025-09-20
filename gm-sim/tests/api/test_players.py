import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.db import get_db
from app.main import app
from app.models import Base, Player, Team


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
async def seed_players(test_sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with test_sessionmaker() as session:
        team = Team(name="Test Team", abbr="TST")
        session.add(team)
        await session.flush()

        session.add_all(
            [
                Player(name="Alice Runner", pos="RB", team_id=team.id, ovr=78),
                Player(name="Bob Thrower", pos="QB", team_id=team.id, ovr=82),
                Player(name="Cal Receiver", pos="WR", team_id=None, ovr=70),
            ]
        )
        await session.commit()


@pytest_asyncio.fixture
async def client(
    test_sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_players_list_200(client: AsyncClient, seed_players: None) -> None:
    response = await client.get("/players/")

    assert response.status_code == 200
    payload = response.json()

    assert payload["page"] == 1
    assert payload["page_size"] == 25
    assert payload["total"] == 3
    assert {player["name"] for player in payload["items"]} == {
        "Alice Runner",
        "Bob Thrower",
        "Cal Receiver",
    }


@pytest.mark.asyncio
async def test_players_list_with_filters(client: AsyncClient, seed_players: None) -> None:
    response = await client.get("/players/", params={"position": "QB", "page_size": 1})

    assert response.status_code == 200
    payload = response.json()

    assert payload["total"] == 1
    assert payload["items"][0]["name"] == "Bob Thrower"
    assert payload["page_size"] == 1


@pytest.mark.asyncio
async def test_players_list_with_search_and_team_filter(
    client: AsyncClient, seed_players: None
) -> None:
    response = await client.get(
        "/players/",
        params={"search": "run", "team_id": 1},
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["total"] == 1
    assert payload["items"][0]["name"] == "Alice Runner"


@pytest.mark.asyncio
async def test_players_list_empty_page(client: AsyncClient, seed_players: None) -> None:
    response = await client.get("/players/", params={"page": 2, "page_size": 5})

    assert response.status_code == 200
    payload = response.json()

    assert payload["items"] == []
    assert payload["total"] == 3
    assert payload["page"] == 2


@pytest.mark.asyncio
async def test_players_list_page_size_limit(client: AsyncClient, seed_players: None) -> None:
    response = await client.get("/players/", params={"page_size": 101})

    assert response.status_code == 422
    payload = response.json()
    assert payload["detail"][0]["type"] == "less_than_equal"
