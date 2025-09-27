from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base, Player, Team
from app.schemas import FreeAgentBiddingRequest, FreeAgentOffer
from app.services.free_agency import evaluate_free_agent_bidding


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
async def test_bidding_ranks_highest_offer(session_factory):
    async with session_factory() as session:
        team_a = Team(name="High Rollers", abbr="HR", elo=1600, scheme_off="West Coast")
        team_b = Team(name="Steady", abbr="STD", elo=1500, scheme_off="Power Run")
        session.add_all([team_a, team_b])
        await session.flush()

        player = Player(name="Star Receiver", pos="WR", team_id=team_b.id)
        session.add(player)
        await session.commit()

        request = FreeAgentBiddingRequest(
            player_id=player.id,
            start_year=2026,
            offers=[
                FreeAgentOffer(
                    team_id=team_a.id,
                    total_value=80_000_000,
                    years=4,
                    signing_bonus=12_000_000,
                    guarantees_total=45_000_000,
                    pitch="All-pro QB and pass-happy attack",
                    scheme_pitch="West Coast",
                ),
                FreeAgentOffer(
                    team_id=team_b.id,
                    total_value=60_000_000,
                    years=4,
                    signing_bonus=5_000_000,
                    guarantees_total=30_000_000,
                    pitch="Return to familiarity",
                    scheme_pitch="Power",
                ),
            ],
            prefer_contender=True,
            loyalty_weight=1.5,
        )

        result = await evaluate_free_agent_bidding(session, request)
        assert result.winning_team_id == team_a.id
        assert result.winning_offer.score >= result.ranked_offers[1].score
        assert "coaching" in result.rationale.lower()
