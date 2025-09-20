"""Persistent franchise state management utilities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DraftPick, FranchiseState, Player, Transaction
from app.services.injuries import PlayerParticipation

DEFAULT_SEASON = 2024


@dataclass(slots=True)
class GameStateSnapshot:
    """Serializable representation of the franchise state."""

    current_season: int
    current_week: int
    rosters: Dict[str, List[Dict[str, Any]]]
    free_agents: List[Dict[str, Any]]
    draft_picks_used: List[int]
    trades: List[Dict[str, Any]]


class GameStateStore:
    """Coordinates persistent state across seasons, trades, and rosters."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_state(self) -> FranchiseState:
        state = await self._session.get(FranchiseState, 1)
        if state is None:
            state = FranchiseState(
                id=1,
                current_season=DEFAULT_SEASON,
                current_week=0,
                roster_snapshot={},
                free_agents=[],
                draft_picks_used=[],
                trades=[],
            )
            self._session.add(state)
            await self._session.commit()
            await self._session.refresh(state)
        return state

    async def snapshot(self) -> GameStateSnapshot:
        """Persist the latest state snapshot and return it."""

        state = await self.ensure_state()
        rosters, free_agents = await self._collect_rosters()
        draft_picks_used = await self._collect_used_picks()
        trades = await self._collect_recent_trades()

        state.roster_snapshot = rosters
        state.free_agents = free_agents
        state.draft_picks_used = draft_picks_used
        state.trades = trades
        await self._session.commit()
        await self._session.refresh(state)

        return GameStateSnapshot(
            current_season=state.current_season,
            current_week=state.current_week,
            rosters=rosters,
            free_agents=free_agents,
            draft_picks_used=draft_picks_used,
            trades=trades,
        )

    async def snapshot_for_game(self, team_ids: Sequence[int]) -> Dict[str, Any]:
        """Return an abridged snapshot for narrative prompts."""

        snapshot = await self.snapshot()
        relevant_rosters: Dict[str, List[Dict[str, Any]]] = {}
        for team_id in team_ids:
            relevant_rosters[str(team_id)] = snapshot.rosters.get(str(team_id), [])
        return {
            "current_season": snapshot.current_season,
            "current_week": snapshot.current_week,
            "rosters": relevant_rosters,
            "free_agents": snapshot.free_agents,
            "draft_picks_used": snapshot.draft_picks_used,
            "recent_trades": snapshot.trades,
        }

    async def participant_rosters(self) -> Dict[int, List[PlayerParticipation]]:
        """Build PlayerParticipation objects for each team from the database."""

        result = await self._session.execute(select(Player))
        players: List[Player] = list(result.scalars())
        rosters: Dict[int, List[PlayerParticipation]] = {}
        for player in players:
            if player.team_id is None:
                continue
            rosters.setdefault(player.team_id, []).append(
                PlayerParticipation(
                    player_id=player.id,
                    position=player.pos or "",  # type: ignore[arg-type]
                    snaps=60,
                    player_name=player.name,
                )
            )
        return rosters

    async def update_after_games(self, *, season: int, week: int) -> GameStateSnapshot:
        """Record the latest week and persist a refreshed snapshot."""

        state = await self.ensure_state()
        state.current_season = season
        state.current_week = week
        await self._session.commit()
        return await self.snapshot()

    async def advance_offseason(self) -> GameStateSnapshot:
        """Advance to the next season and refresh the snapshot."""

        state = await self.ensure_state()
        state.current_season += 1
        state.current_week = 0
        await self._session.commit()
        return await self.snapshot()

    async def _collect_rosters(
        self,
    ) -> tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
        result = await self._session.execute(select(Player))
        players: List[Player] = list(result.scalars())

        rosters: Dict[str, List[Dict[str, Any]]] = {}
        free_agents: List[Dict[str, Any]] = []
        for player in players:
            payload = {
                "player_id": player.id,
                "name": player.name,
                "position": player.pos,
                "team_id": player.team_id,
            }
            if player.team_id is None:
                free_agents.append(payload)
            else:
                rosters.setdefault(str(player.team_id), []).append(payload)
        return rosters, free_agents

    async def _collect_used_picks(self) -> List[int]:
        result = await self._session.execute(select(DraftPick).where(DraftPick.used.is_(True)))
        picks = [pick.id for pick in result.scalars()]
        return picks

    async def _collect_recent_trades(self) -> List[Dict[str, Any]]:
        result = await self._session.execute(
            select(Transaction).order_by(Transaction.timestamp.desc()).limit(10)
        )
        trades: List[Dict[str, Any]] = []
        for trade in result.scalars():
            timestamp: datetime | None = trade.timestamp
            trades.append(
                {
                    "transaction_id": trade.id,
                    "type": trade.type,
                    "team_from": trade.team_from,
                    "team_to": trade.team_to,
                    "timestamp": timestamp.isoformat() if timestamp else None,
                }
            )
        return trades


def attach_names_to_participants(
    roster_snapshot: Mapping[str, Iterable[Mapping[str, Any]]],
    participations: MutableMapping[int, List[PlayerParticipation]],
) -> None:
    """Ensure PlayerParticipation entries carry player names for grounding."""

    for team_key, players in roster_snapshot.items():
        try:
            team_id = int(team_key)
        except (TypeError, ValueError):
            continue
        team_roster = participations.get(team_id)
        if not team_roster:
            continue
        info_lookup = {player["player_id"]: player for player in players if "player_id" in player}
        for participant in team_roster:
            if participant.player_name:
                continue
            player_info = info_lookup.get(participant.player_id)
            if player_info:
                participant.player_name = str(player_info.get("name", ""))
