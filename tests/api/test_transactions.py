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
from app.models import Base
from app.routers import transactions
from app.services.llm import TradeDialogue


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
async def client(
    test_sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


class StubNarrativeClient:
    def __init__(self) -> None:
        self.contexts: list[dict] = []
        self.api_key = "stub-key"

    async def generate_trade_dialogue(self, context: dict) -> TradeDialogue:
        self.contexts.append(context)
        return TradeDialogue(
            summary="Stub narrative summary",
            team_positions={
                "team_a": "Team A wants future picks",
                "team_b": "Team B is focused on win-now talent",
            },
            negotiation_points=[
                "Consider adding a 2026 second-rounder",
                "Discuss conditional pick swap",
            ],
        )


class ErrorNarrativeClient:
    api_key = "stub-key"

    async def generate_trade_dialogue(self, context: dict) -> TradeDialogue:
        raise ValueError("invalid narrative payload")


@pytest_asyncio.fixture
async def narrative_override() -> AsyncIterator[StubNarrativeClient]:
    client = StubNarrativeClient()
    app.dependency_overrides[transactions.get_narrative_client] = lambda: client
    try:
        yield client
    finally:
        app.dependency_overrides.pop(transactions.get_narrative_client, None)


@pytest.mark.asyncio
async def test_evaluate_trade_without_narrative(client: AsyncClient) -> None:
    response = await client.post(
        "/transactions/evaluate-trade",
        json={
            "team_a_name": "Chicago Bears",
            "team_b_name": "Buffalo Bills",
            "team_a_assets": [1, 72],
            "team_b_assets": [28, 60, 92],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["team_a_value"] > 0
    assert payload["team_b_value"] > 0
    assert payload["delta"] == payload["team_a_value"] - payload["team_b_value"]
    assert payload["narrative"] is None


@pytest.mark.asyncio
async def test_evaluate_trade_with_narrative(
    client: AsyncClient, narrative_override: StubNarrativeClient
) -> None:
    response = await client.post(
        "/transactions/evaluate-trade",
        json={
            "team_a_name": "Chicago Bears",
            "team_b_name": "Buffalo Bills",
            "team_a_assets": [1, 72],
            "team_b_assets": [28, 60, 92],
            "include_narrative": True,
            "tasks_completed": "Draft value breakdown completed",
            "tasks_remaining": "Decide on counter-offer",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["narrative"]["summary"] == "Stub narrative summary"
    assert len(payload["narrative"]["negotiation_points"]) == 2
    assert narrative_override.contexts
    context = narrative_override.contexts[0]
    assert context["evaluation"]["team_a_value"] == payload["team_a_value"]


@pytest.mark.asyncio
async def test_evaluate_trade_narrative_error_returns_502(client: AsyncClient) -> None:
    app.dependency_overrides[transactions.get_narrative_client] = lambda: ErrorNarrativeClient()
    try:
        response = await client.post(
            "/transactions/evaluate-trade",
            json={
                "team_a_name": "Chicago Bears",
                "team_b_name": "Buffalo Bills",
                "team_a_assets": [1],
                "team_b_assets": [28],
                "include_narrative": True,
            },
        )
    finally:
        app.dependency_overrides.pop(transactions.get_narrative_client, None)

    assert response.status_code == 502
    payload = response.json()
    assert "invalid narrative" in payload["detail"]


@pytest.mark.asyncio
async def test_evaluate_trade_requires_narrative_configuration(client: AsyncClient) -> None:
    response = await client.post(
        "/transactions/evaluate-trade",
        json={
            "team_a_name": "Chicago Bears",
            "team_b_name": "Buffalo Bills",
            "team_a_assets": [1],
            "team_b_assets": [28],
            "include_narrative": True,
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Narrative service is not configured"
