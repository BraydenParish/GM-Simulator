import os
import tempfile
from typing import Dict

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.db import get_db
from app.main import app
from app.models import Base, Contract, Player, Team


@pytest.fixture
async def test_db():
    fd, path = tempfile.mkstemp(prefix="contracts-test-", suffix=".db")
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
                Team(id=1, name="Caps", abbr="CAP", cap_space=7_000_000, cap_year=2027),
                Team(
                    id=2, name="Tight", abbr="TIG", cap_space=1_000_000, cap_year=2027
                ),
            ]
        )
        session.add_all(
            [
                Player(id=10, name="Free Agent", pos="WR", team_id=None),
                Player(id=11, name="Depth Player", pos="RB", team_id=None),
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


def _build_contract_payload(overrides: Dict | None = None) -> Dict:
    payload = {
        "player_id": 10,
        "team_id": 1,
        "start_year": 2027,
        "end_year": 2029,
        "base_salary_yearly": {2027: 2_000_000, 2028: 2_200_000, 2029: 2_400_000},
        "signing_bonus_total": 6_000_000,
        "guarantees_total": 4_000_000,
        "void_years": 1,
    }
    if overrides:
        payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_sign_contract_proration_and_cap_space(client: AsyncClient, test_db):
    response = await client.post("/contracts/sign", json=_build_contract_payload())
    assert response.status_code == 200
    data = response.json()
    assert data["cap_hits_yearly"]["2027"] == 3_500_000
    assert data["dead_money_yearly"]["2027"] == 6_000_000
    assert data["dead_money_yearly"]["2030"] == 1_500_000

    async with test_db() as session:
        team = await session.get(Team, 1)
        assert team.cap_space == 3_500_000
        contract = (
            await session.execute(select(Contract).where(Contract.player_id == 10))
        ).scalar_one()
        assert contract.base_salary_yearly["2028"] == 2_200_000


@pytest.mark.asyncio
async def test_sign_contract_enforces_cap_limits(client: AsyncClient):
    payload = _build_contract_payload({"team_id": 2, "player_id": 11})
    response = await client.post("/contracts/sign", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_cut_contract_pre_and_post_june1(client: AsyncClient, test_db):
    await client.post("/contracts/sign", json=_build_contract_payload())

    pre_response = await client.post(
        "/contracts/cut",
        json={
            "player_id": 10,
            "team_id": 1,
            "league_year": 2027,
            "post_june1": False,
        },
    )
    assert pre_response.status_code == 200
    pre_data = pre_response.json()
    assert pre_data["dead_money_current"] == 6_000_000
    assert pre_data["freed_cap"] == -2_500_000

    async with test_db() as session:
        team = await session.get(Team, 1)
        team.cap_space = 7_000_000
        await session.commit()

    await client.post("/contracts/sign", json=_build_contract_payload())

    post_response = await client.post(
        "/contracts/cut",
        json={
            "player_id": 10,
            "team_id": 1,
            "league_year": 2027,
            "post_june1": True,
        },
    )
    assert post_response.status_code == 200
    post_data = post_response.json()
    assert post_data["dead_money_current"] == 1_500_000
    assert post_data["dead_money_future"] == 4_500_000
    assert post_data["freed_cap"] == 2_000_000

    async with test_db() as session:
        contracts = (
            (await session.execute(select(Contract).where(Contract.team_id == 1)))
            .scalars()
            .all()
        )
        assert not contracts
        team = await session.get(Team, 1)
        assert team.cap_space == 5_500_000
