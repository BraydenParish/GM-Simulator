import os
import sys
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.db import get_db
from app.main import app
from app.models import Base, Player, Team


@pytest.fixture
async def test_db():
    fd, path = tempfile.mkstemp(prefix="players-test-", suffix=".db")
    os.close(fd)
    database_url = f"sqlite+aiosqlite:///{path}"
    engine = create_async_engine(
        database_url,
        future=True,
        poolclass=NullPool,
    )
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        session.add_all(
            [
                Team(id=1, name="Alpha", abbr="ALP"),
                Team(id=2, name="Beta", abbr="BET"),
            ]
        )
        session.add_all(
            [
                Player(name="Aaron Able", pos="QB", team_id=1, ovr=90),
                Player(name="Boris Bold", pos="WR", team_id=1, ovr=82),
                Player(name="Charlie Calm", pos="QB", team_id=2, ovr=78),
                Player(name="Dana Daring", pos="RB", team_id=None, ovr=75),
            ]
        )
        await session.commit()

    async def override_get_db():
        async with async_session() as session:
            yield session  # pragma: no cover - exercised in tests

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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as test_client:
        yield test_client


@pytest.mark.asyncio
async def test_players_list_200(client: AsyncClient):
    response = await client.get("/players/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 4
    assert payload["page"] == 1
    assert payload["page_size"] == 25
    assert len(payload["items"]) == 4
    assert {p["name"] for p in payload["items"]} == {
        "Aaron Able",
        "Boris Bold",
        "Charlie Calm",
        "Dana Daring",
    }


@pytest.mark.asyncio
async def test_players_filters_and_pagination(client: AsyncClient):
    response = await client.get("/players/", params={"team_id": 1, "position": "wr"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["name"] == "Boris Bold"

    response = await client.get(
        "/players/",
        params={"search": "char", "page_size": 1, "page": 1},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["name"] == "Charlie Calm"
    assert payload["page_size"] == 1


@pytest.mark.asyncio
async def test_players_validation(client: AsyncClient):
    response = await client.get("/players/", params={"page": 0})
    assert response.status_code == 422
    payload = response.json()
    assert payload["detail"]
