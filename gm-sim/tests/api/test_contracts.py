from collections.abc import AsyncIterator, Iterator
from typing import Any, Dict

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import get_db
from app.main import app
from app.models import Base, FranchiseState, Player, Team
from app.routers import contracts as contracts_router
from app.services.llm import FreeAgentPitch


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


@pytest_asyncio.fixture
async def client(
    test_sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def narrative_stub() -> Iterator[Dict[str, Any]]:
    pitch = FreeAgentPitch(
        summary="Veteran playmaker intrigued by offensive fit.",
        team_pitch="Team emphasizes Super Bowl window and feature role.",
        player_reaction="Agent wants clarity on guarantees and incentives.",
        next_steps=["Team prepares updated guarantee structure", "Agent schedules review call"],
    )

    class StubClient:
        def __init__(self) -> None:
            self.calls = 0
            self.last_context: Dict[str, Any] | None = None
            self.api_key = "stub-key"

        async def generate_free_agent_pitch(self, context: Dict[str, Any]) -> FreeAgentPitch:
            self.calls += 1
            self.last_context = context
            return pitch

    stub = StubClient()
    app.dependency_overrides[contracts_router.get_narrative_client] = lambda: stub
    try:
        yield {"stub": stub, "pitch": pitch}
    finally:
        app.dependency_overrides.pop(contracts_router.get_narrative_client, None)


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


@pytest.mark.asyncio
async def test_contract_updates_state_store(
    client: AsyncClient,
    test_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with test_sessionmaker() as session:
        team = Team(name="State Sync", abbr="STS", cap_space=25_000_000, cap_year=2025)
        player = Player(name="Future Star", pos="QB", ovr=85)
        session.add_all([team, player])
        await session.commit()

    sign_response = await client.post(
        "/contracts/sign",
        json={
            "player_id": 1,
            "team_id": 1,
            "start_year": 2025,
            "end_year": 2026,
            "base_salary_yearly": {2025: 2_000_000, 2026: 3_000_000},
            "signing_bonus_total": 6_000_000,
            "guarantees_total": 5_000_000,
        },
    )
    assert sign_response.status_code == 200

    async with test_sessionmaker() as session:
        state = await session.get(FranchiseState, 1)
        assert state is not None
        roster_entries = state.roster_snapshot.get("1", [])
        assert any(entry.get("player_id") == 1 for entry in roster_entries)
        assert all(agent.get("player_id") != 1 for agent in state.free_agents)

    contract_id = sign_response.json()["id"]
    cut_response = await client.post(
        "/contracts/cut",
        json={"contract_id": contract_id, "league_year": 2025, "post_june1": False},
    )
    assert cut_response.status_code == 200

    async with test_sessionmaker() as session:
        state = await session.get(FranchiseState, 1)
        assert state is not None
        roster_entries = state.roster_snapshot.get("1", [])
        assert all(entry.get("player_id") != 1 for entry in roster_entries)
        assert any(agent.get("player_id") == 1 for agent in state.free_agents)


@pytest.mark.asyncio
async def test_negotiate_free_agent_offer_returns_narrative(
    client: AsyncClient, narrative_stub: Dict[str, Any]
) -> None:
    response = await client.post(
        "/contracts/negotiate",
        json={
            "team_name": "Metropolis Meteors",
            "player_name": "Star Receiver",
            "player_position": "WR",
            "player_age": 29,
            "offer_years": 4,
            "offer_total_value": 84_000_000,
            "signing_bonus": 20_000_000,
            "guarantees": 60_000_000,
            "incentives": ["Pro Bowl", "Yards leader"],
            "player_market_apy": 18_500_000,
            "tasks_completed": "Initial offer drafted.",
            "tasks_remaining": "Await agent response.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["team_name"] == "Metropolis Meteors"
    assert payload["player_name"] == "Star Receiver"
    metrics = payload["metrics"]
    assert metrics["apy"] == pytest.approx(21_000_000)
    assert metrics["signing_bonus_proration"] == pytest.approx(5_000_000)
    assert metrics["guaranteed_percentage"] == pytest.approx(60_000_000 / 84_000_000)
    assert metrics["market_delta"] == pytest.approx(2_500_000)
    assert metrics["risk_flags"] == []

    narrative = payload["narrative"]
    expected = narrative_stub["pitch"]
    assert narrative["summary"] == expected.summary
    assert narrative["team_pitch"] == expected.team_pitch
    assert narrative["player_reaction"] == expected.player_reaction
    assert len(narrative["next_steps"]) == len(expected.next_steps)

    stub_client = narrative_stub["stub"]
    assert stub_client.calls == 1


@pytest.mark.asyncio
async def test_negotiate_free_agent_offer_without_narrative(
    client: AsyncClient,
) -> None:
    app.dependency_overrides[contracts_router.get_narrative_client] = lambda: None
    try:
        response = await client.post(
            "/contracts/negotiate",
            json={
                "team_name": "Gotham Knights",
                "player_name": "Depth Corner",
                "player_position": "CB",
                "offer_years": 1,
                "offer_total_value": 2_500_000,
                "signing_bonus": 500_000,
                "guarantees": 1_500_000,
                "include_narrative": False,
            },
        )
    finally:
        app.dependency_overrides.pop(contracts_router.get_narrative_client, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"]["apy"] == pytest.approx(2_500_000)
    assert payload["narrative"] is None


@pytest.mark.asyncio
async def test_negotiate_free_agent_offer_requires_narrative_client(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/contracts/negotiate",
        json={
            "team_name": "Central City",
            "player_name": "Pass Rusher",
            "player_position": "EDGE",
            "offer_years": 3,
            "offer_total_value": 45_000_000,
            "signing_bonus": 25_000_000,
            "guarantees": 40_000_000,
        },
    )

    assert response.status_code == 503
    assert "Narrative service is not configured" in response.text
