import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import get_db
from app.main import app
from app.models import Base, Game, InjuryReport, Player, Team
from app.services.injuries import InjuryEngine, InjuryEvent


@pytest.fixture
async def test_sessionmaker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
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
async def client(test_sessionmaker):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_simulated_injuries_are_persisted_and_exposed(
    client,
    test_sessionmaker,
    monkeypatch,
):
    async with test_sessionmaker() as session:
        teams = [
            Team(name="Alpha", abbr="ALP"),
            Team(name="Bravo", abbr="BRV"),
        ]
        session.add_all(teams)
        await session.flush()

        players = [
            Player(name="Alpha QB", pos="QB", team_id=teams[0].id),
            Player(name="Bravo QB", pos="QB", team_id=teams[1].id),
        ]
        session.add_all(players)
        await session.commit()
        alpha_qb_id = players[0].id
        alpha_team_id = teams[0].id

    call_counter = {"count": 0}

    def fake_simulate_game(self, team_id, participants):
        call_counter["count"] += 1
        participant_list = list(participants)
        if call_counter["count"] == 1 and participant_list:
            target = participant_list[0]
            return [
                InjuryEvent(
                    player_id=target.player_id,
                    team_id=team_id,
                    severity="moderate",
                    weeks_out=3,
                    occurred_snap=12,
                    injury_type="Test injury",
                )
            ]
        return []

    monkeypatch.setattr(InjuryEngine, "simulate_game", fake_simulate_game)

    response = await client.post(
        "/seasons/simulate-full",
        params={"season": 2025, "generate_narratives": False},
    )
    assert response.status_code == 200

    report_response = await client.get("/injuries/report", params={"season": 2025})
    assert report_response.status_code == 200
    report_payload = report_response.json()
    assert report_payload["season"] == 2025
    assert report_payload["injuries"], "Expected at least one persisted injury"
    injury_entry = report_payload["injuries"][0]
    assert injury_entry["player_id"] == alpha_qb_id
    assert injury_entry["player_name"] == "Alpha QB"
    assert injury_entry["team_abbr"] == "ALP"
    assert injury_entry["expected_return_week"] == injury_entry["week"] + 3

    team_response = await client.get(
        "/injuries/report",
        params={"season": 2025, "team_id": alpha_team_id},
    )
    assert team_response.status_code == 200
    assert team_response.json()["injuries"]

    async with test_sessionmaker() as session:
        game_row = await session.execute(select(Game))
        stored_game = game_row.scalar_one()
        assert stored_game.injuries_json
        injury_payload = stored_game.injuries_json[0]
        assert injury_payload["player_id"] == alpha_qb_id
        assert injury_payload["expected_return_week"] == injury_payload["week"] + 3

        report_row = await session.execute(select(InjuryReport))
        stored_report = report_row.scalar_one()
        assert stored_report.player_id == alpha_qb_id
        assert stored_report.team_id == alpha_team_id
        assert stored_report.expected_return_week == stored_report.week + 3
