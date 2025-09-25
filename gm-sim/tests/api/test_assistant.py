import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import get_db
from app.main import app
from app.models import Base, Game, Player, Schedule, Standing, Team


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
async def test_free_agent_projection_and_signing_flow(client: AsyncClient, test_sessionmaker):
    async with test_sessionmaker() as session:
        alpha = Team(name="Alpha", abbr="ALP", cap_space=75_000_000)
        beta = Team(name="Beta", abbr="BET", cap_space=60_000_000)
        session.add_all([alpha, beta])
        await session.commit()
        await session.refresh(alpha)
        await session.refresh(beta)
        beta_id = beta.id

        dak = Player(name="Dak Prescott", pos="QB", team_id=alpha.id, age=31, ovr=92)
        free_agent = Player(name="Jordan Fair", pos="WR", team_id=None, age=27, ovr=84, stamina=88)
        session.add_all([dak, free_agent])
        await session.commit()
        await session.refresh(free_agent)
        free_agent_id = free_agent.id

    projection_resp = await client.get(
        "/assistant/free-agents/projections",
        params={"season": 2025, "limit": 2},
    )
    assert projection_resp.status_code == 200
    projection_payload = projection_resp.json()
    assert any(entry["name"] == "Dak Prescott" and entry["player_id"] is not None for entry in projection_payload)

    pool_resp = await client.get("/assistant/free-agents/pool", params={"limit": 5})
    assert pool_resp.status_code == 200
    pool_payload = pool_resp.json()
    assert any(entry["player_id"] == free_agent_id for entry in pool_payload)

    sign_resp = await client.post(
        "/assistant/free-agents/sign",
        json={
            "player_id": free_agent_id,
            "team_id": beta_id,
            "start_year": 2025,
            "years": 2,
            "total_value": 12_000_000,
            "signing_bonus": 4_000_000,
        },
    )
    assert sign_resp.status_code == 200
    contract_payload = sign_resp.json()
    assert contract_payload["contract"]["team_id"] == beta_id

    async with test_sessionmaker() as session:
        updated_player = await session.get(Player, free_agent_id)
        assert updated_player.team_id == beta_id

    refreshed_pool = await client.get("/assistant/free-agents/pool", params={"limit": 5})
    assert refreshed_pool.status_code == 200
    assert all(entry["player_id"] != free_agent_id for entry in refreshed_pool.json())


@pytest.mark.asyncio
async def test_dashboard_and_highlights_surface_recent_games(client: AsyncClient, test_sessionmaker):
    game_id = None
    async with test_sessionmaker() as session:
        home = Team(name="Home", abbr="HOM", cap_space=80_000_000)
        away = Team(name="Away", abbr="AWY", cap_space=80_000_000)
        session.add_all([home, away])
        await session.commit()
        await session.refresh(home)
        await session.refresh(away)

        schedule_week1 = Schedule(season=2025, week=1, home_team_id=home.id, away_team_id=away.id)
        schedule_week2 = Schedule(season=2025, week=2, home_team_id=away.id, away_team_id=home.id)
        drives = [
            {"team": "home", "result": "TD", "yards": 75, "minutes": 2.5},
            {"team": "away", "result": "Punt", "yards": 35, "minutes": 3.0},
            {"team": "home", "result": "Turnover", "yards": 0, "minutes": 1.0},
        ]
        game = Game(
            season=2025,
            week=1,
            home_team_id=home.id,
            away_team_id=away.id,
            home_score=31,
            away_score=17,
            box_json={"drives": drives},
            narrative_recap="Home team dominates early",
        )
        standing_home = Standing(
            season=2025,
            team_id=home.id,
            wins=1,
            losses=0,
            ties=0,
            pf=31,
            pa=17,
            elo=1525,
        )
        standing_away = Standing(
            season=2025,
            team_id=away.id,
            wins=0,
            losses=1,
            ties=0,
            pf=17,
            pa=31,
            elo=1475,
        )
        session.add_all([schedule_week1, schedule_week2, game, standing_home, standing_away])
        await session.commit()
        await session.refresh(game)
        game_id = game.id

    dashboard_resp = await client.get(
        "/assistant/season-dashboard",
        params={"season": 2025, "free_agent_limit": 2},
    )
    assert dashboard_resp.status_code == 200
    payload = dashboard_resp.json()
    assert payload["progress"]["next_week"] == 2
    assert payload["progress"]["last_completed_week"] == 1
    assert payload["upcoming_games"]
    assert payload["recent_games"], "expected recent games to be surfaced"
    assert payload["recent_games"][0]["highlights"], "highlights should not be empty"

    highlight_resp = await client.get(f"/assistant/games/{game_id}/highlights")
    assert highlight_resp.status_code == 200
    highlight_payload = highlight_resp.json()
    assert highlight_payload["highlights"]
    assert any(h["descriptor"] == "touchdown" for h in highlight_payload["highlights"])
