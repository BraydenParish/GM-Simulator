from collections import defaultdict
from typing import AsyncIterator, Dict

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base, DraftPick, Player, Team, Transaction
from app.services.injuries import PlayerParticipation
from app.services.state import GameStateStore, attach_names_to_participants


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
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
async def test_snapshot_tracks_rosters_and_trades(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        chiefs = Team(name="Kansas City Chiefs", abbr="KC")
        bills = Team(name="Buffalo Bills", abbr="BUF")
        session.add_all([chiefs, bills])
        await session.flush()

        session.add_all(
            [
                Player(id=1, name="Patrick Mahomes", pos="QB", team_id=chiefs.id),
                Player(id=2, name="Josh Allen", pos="QB", team_id=bills.id),
                Player(id=3, name="Free Agent WR", pos="WR", team_id=None),
            ]
        )
        session.add(
            DraftPick(id=10, year=2025, round=1, overall=5, owned_by_team_id=chiefs.id, used=True)
        )
        session.add(
            Transaction(
                type="trade",
                team_from=chiefs.id,
                team_to=bills.id,
                payload_json={"player_id": 3},
            )
        )
        await session.commit()

        store = GameStateStore(session)
        snapshot = await store.snapshot()

        assert str(chiefs.id) in snapshot.rosters
        chiefs_roster = snapshot.rosters[str(chiefs.id)]
        assert any(player["player_id"] == 1 for player in chiefs_roster)

        free_agent_ids = {player["player_id"] for player in snapshot.free_agents}
        assert 3 in free_agent_ids

        assert snapshot.draft_picks_used == [10]
        assert snapshot.trades
        assert snapshot.trades[0]["team_from"] == chiefs.id


@pytest.mark.asyncio
async def test_state_updates_after_roster_changes(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        team_one = Team(name="Team One", abbr="ONE")
        team_two = Team(name="Team Two", abbr="TWO")
        session.add_all([team_one, team_two])
        await session.flush()

        player = Player(id=5, name="Journeyman QB", pos="QB", team_id=team_one.id)
        session.add(player)
        await session.commit()

        store = GameStateStore(session)
        initial = await store.snapshot()
        assert any(p["player_id"] == 5 for p in initial.rosters[str(team_one.id)])

        player.team_id = team_two.id
        await session.commit()

        updated = await store.snapshot()
        assert all(p["player_id"] != 5 for p in updated.rosters.get(str(team_one.id), []))
        assert any(p["player_id"] == 5 for p in updated.rosters[str(team_two.id)])

        roster_map: Dict[int, list[PlayerParticipation]] = defaultdict(list)
        roster_map[team_two.id].append(PlayerParticipation(player_id=5, position="QB", snaps=60))
        attach_names_to_participants(updated.rosters, roster_map)
        assert roster_map[team_two.id][0].player_name == "Journeyman QB"


@pytest.mark.asyncio
async def test_week_and_season_progression(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        team = Team(name="Team", abbr="TM")
        session.add(team)
        await session.flush()

        session.add(Player(id=11, name="Linebacker", pos="LB", team_id=team.id))
        await session.commit()

        store = GameStateStore(session)
        snapshot = await store.update_after_games(season=2024, week=3)
        assert snapshot.current_week == 3
        assert snapshot.current_season == 2024

        advanced = await store.advance_offseason()
        assert advanced.current_week == 0
        assert advanced.current_season == 2025

        game_snapshot = await store.snapshot_for_game([team.id])
        assert game_snapshot["rosters"][str(team.id)]

        participants = await store.participant_rosters()
        assert participants[team.id][0].player_name == "Linebacker"
