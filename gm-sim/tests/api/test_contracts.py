from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import get_db
from app.main import app
from app.models import Base, Player, Team


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
async def seed_team_and_player(
    test_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with test_sessionmaker() as session:
        team = Team(name="Cap City", abbr="CAP", cap_space=20_000_000, cap_year=2025)
        session.add(team)
        await session.flush()
        player = Player(name="Veteran Star", pos="WR", team_id=None, ovr=88)
        session.add(player)
        await session.commit()


@pytest.fixture
async def client(
    test_sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_sign_contract_success(client: AsyncClient, seed_team_and_player: None) -> None:
    response = await client.post(
        "/contracts/sign",
        json={
            "player_id": 1,
            "team_id": 1,
            "start_year": 2025,
            "end_year": 2027,
            "base_salary_yearly": {2025: 1_000_000, 2026: 2_000_000, 2027: 3_000_000},
            "signing_bonus_total": 9_000_000,
            "guarantees_total": 6_000_000,
            "void_years": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["apy"] == 5_000_000.0
    assert payload["cap_hits_yearly"] == {
        "2025": 3_250_000,
        "2026": 4_250_000,
        "2027": 5_250_000,
    }
    assert payload["dead_money_yearly"]["2025"] == 10_000_000
    assert payload["dead_money_yearly"]["2028"] == 2_250_000


@pytest.mark.asyncio
async def test_sign_contract_enforces_cap(
    client: AsyncClient, test_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    async with test_sessionmaker() as session:
        team = Team(name="Tight Cap", abbr="TAP", cap_space=3_000_000, cap_year=2025)
        player = Player(name="Cap Heavy", pos="QB", ovr=90)
        session.add_all([team, player])
        await session.commit()

    response = await client.post(
        "/contracts/sign",
        json={
            "player_id": 1,
            "team_id": 1,
            "start_year": 2025,
            "end_year": 2026,
            "base_salary_yearly": {2025: 2_000_000, 2026: 2_500_000},
            "signing_bonus_total": 4_000_000,
            "guarantees_total": 4_000_000,
        },
    )

    assert response.status_code == 422
    assert "Insufficient cap space" in response.text


@pytest.mark.asyncio
async def test_cut_contract_pre_and_post_june1(
    client: AsyncClient, seed_team_and_player: None
) -> None:
    sign_response = await client.post(
        "/contracts/sign",
        json={
            "player_id": 1,
            "team_id": 1,
            "start_year": 2025,
            "end_year": 2027,
            "base_salary_yearly": {2025: 1_000_000, 2026: 2_000_000, 2027: 3_000_000},
            "signing_bonus_total": 9_000_000,
            "guarantees_total": 6_000_000,
            "void_years": 1,
        },
    )
    assert sign_response.status_code == 200
    first_contract_id = sign_response.json()["id"]

    cut_response = await client.post(
        "/contracts/cut",
        json={"contract_id": first_contract_id, "league_year": 2025, "post_june1": False},
    )
    assert cut_response.status_code == 200
    payload = cut_response.json()
    assert payload["dead_money_current_year"] == 10_000_000
    assert payload["dead_money_next_year"] == 0
    assert payload["cap_savings"] == -6_750_000
    assert payload["team_cap_space"] == 10_000_000

    # Re-sign the player for a post-June 1 test
    resign_response = await client.post(
        "/contracts/sign",
        json={
            "player_id": 1,
            "team_id": 1,
            "start_year": 2025,
            "end_year": 2027,
            "base_salary_yearly": {2025: 1_000_000, 2026: 2_000_000, 2027: 3_000_000},
            "signing_bonus_total": 9_000_000,
            "guarantees_total": 6_000_000,
            "void_years": 1,
        },
    )
    assert resign_response.status_code == 200
    second_contract_id = resign_response.json()["id"]

    post_june_response = await client.post(
        "/contracts/cut",
        json={"contract_id": second_contract_id, "league_year": 2025, "post_june1": True},
    )
    assert post_june_response.status_code == 200
    post_payload = post_june_response.json()
    assert post_payload["dead_money_current_year"] == 3_250_000
    assert post_payload["dead_money_next_year"] == 6_750_000
    assert post_payload["cap_savings"] == 0
    assert post_payload["team_cap_space"] == 6_750_000
