from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base, Coach, CoachAssignment, Team
from app.services.coaching import CoachingSystem, TeamCoachEffect
from app.services.season import SeasonSimulator, TeamSeed


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield Session
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.mark.asyncio
async def test_coaching_system_builds_effects(session_factory):
    async with session_factory() as session:
        team = Team(
            name="Test Team",
            abbr="TST",
            scheme_off="West Coast",
            scheme_def="Cover 2",
            elo=1505,
        )
        other = Team(name="No Coach", abbr="NC")
        session.add_all([team, other])
        await session.flush()

        coaches = [
            Coach(
                name="Helena Coordinator",
                role_primary="HC",
                scheme="West Coast",
                leadership=4.0,
                development=3.5,
                tactics=4.5,
                discipline=2.0,
                experience_years=12,
            ),
            Coach(
                name="Owen Coordinator",
                role_primary="OC",
                scheme="West Coast",
                leadership=2.5,
                development=4.0,
                tactics=4.2,
                discipline=1.0,
                experience_years=6,
            ),
            Coach(
                name="Dana Coordinator",
                role_primary="DC",
                scheme="Cover 2",
                leadership=3.0,
                development=2.0,
                tactics=3.8,
                discipline=2.5,
                experience_years=9,
            ),
        ]
        session.add_all(coaches)
        await session.flush()

        assignments = [
            CoachAssignment(coach_id=coaches[0].id, team_id=team.id, role="HC"),
            CoachAssignment(coach_id=coaches[1].id, team_id=team.id, role="OC"),
            CoachAssignment(coach_id=coaches[2].id, team_id=team.id, role="DC"),
        ]
        session.add_all(assignments)
        await session.commit()

        system = await CoachingSystem.build(session)
        effect = system.effect_for(team.id)
        assert effect.rating_adjustment() > 0
        assert effect.development_rate_bonus() > 0
        assert any("West Coast" in note for note in effect.notes)

        baseline = system.apply_rating(team.id, 1500)
        assert baseline > 1500
        assert system.apply_rating(other.id, 1500) == 1500


@pytest.mark.asyncio
async def test_season_simulator_embeds_coaching_notes():
    effect = TeamCoachEffect(team_id=1)
    effect.rating_bonus = 5.0
    effect.development_bonus = 2.0
    system = CoachingSystem({1: effect})

    teams = [
        TeamSeed(id=1, name="Alpha", abbr="ALP", rating=90.0),
        TeamSeed(id=2, name="Bravo", abbr="BRV", rating=90.0),
    ]
    simulator = SeasonSimulator(teams, rng_seed=42, coaching_system=system)
    await simulator.simulate_week(1, [(1, 2)])
    logs = simulator.games()
    assert logs
    coaching_notes = logs[0].coaching_notes
    assert coaching_notes.get("home", {}).get("rating_adjustment") == pytest.approx(5.0)
    assert "coaching" in logs[0].narrative_facts
