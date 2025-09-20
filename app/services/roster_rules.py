from __future__ import annotations

from collections.abc import Iterable, Sequence

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GamedayRoster, PracticeSquad, Player

BASE_ROSTER_LIMIT = 53
PRACTICE_SQUAD_BASE_LIMIT = 16
PRACTICE_SQUAD_IPP_LIMIT = 1
MAX_ELEVATIONS_PER_GAME = 2
MAX_ELEVATIONS_PER_PLAYER = 3
OL_POSITIONS = {
    "C",
    "G",
    "LG",
    "LT",
    "OC",
    "OG",
    "OL",
    "OT",
    "RG",
    "RT",
    "T",
}


def ensure_unique_ids(ids: Sequence[int], field: str) -> None:
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=422, detail=f"Duplicate player ids in {field}")


async def ensure_practice_squad_capacity(
    session: AsyncSession,
    team_id: int,
    international_pathway: bool,
) -> None:
    total = await session.scalar(
        select(func.count(PracticeSquad.id)).where(PracticeSquad.team_id == team_id)
    )
    ipp_count = await session.scalar(
        select(func.count(PracticeSquad.id)).where(
            PracticeSquad.team_id == team_id, PracticeSquad.international_pathway.is_(True)
        )
    )
    total = int(total or 0)
    ipp_count = int(ipp_count or 0)

    if international_pathway and ipp_count >= PRACTICE_SQUAD_IPP_LIMIT:
        raise HTTPException(status_code=422, detail="IPP slot already used")

    max_slots = PRACTICE_SQUAD_BASE_LIMIT
    if international_pathway or ipp_count > 0:
        max_slots += PRACTICE_SQUAD_IPP_LIMIT

    if total >= max_slots:
        raise HTTPException(status_code=422, detail="Practice squad is full")


async def ensure_practice_squad_entry_unique(session: AsyncSession, player_id: int) -> None:
    exists = await session.scalar(
        select(func.count(PracticeSquad.id)).where(PracticeSquad.player_id == player_id)
    )
    if (exists or 0) > 0:
        raise HTTPException(status_code=409, detail="Player already on a practice squad")


def compute_required_actives(ol_count: int) -> int:
    return 48 if ol_count >= 8 else 47


async def fetch_team_players(
    session: AsyncSession, team_id: int, player_ids: Iterable[int]
) -> list[Player]:
    ids = list(player_ids)
    if not ids:
        return []
    players = (await session.execute(select(Player).where(Player.id.in_(ids)))).scalars().all()
    missing = set(ids) - {player.id for player in players}
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Players not found: {sorted(missing)}",
        )
    wrong_team = [player.id for player in players if player.team_id != team_id]
    if wrong_team:
        raise HTTPException(
            status_code=422,
            detail=f"Players {sorted(wrong_team)} are not on team {team_id}",
        )
    return list(players)


def count_offensive_line(players: Iterable[Player]) -> int:
    return sum(1 for player in players if (player.pos or "").upper() in OL_POSITIONS)


async def ensure_no_existing_gameday(session: AsyncSession, team_id: int, game_id: int) -> None:
    existing = await session.scalar(
        select(func.count(GamedayRoster.id)).where(
            GamedayRoster.team_id == team_id, GamedayRoster.game_id == game_id
        )
    )
    if (existing or 0) > 0:
        raise HTTPException(status_code=409, detail="Gameday roster already submitted")


async def fetch_practice_squad_entries(
    session: AsyncSession, team_id: int, player_ids: Sequence[int]
) -> dict[int, PracticeSquad]:
    if not player_ids:
        return {}
    entries = (
        await session.execute(
            select(PracticeSquad).where(
                PracticeSquad.team_id == team_id,
                PracticeSquad.player_id.in_(player_ids),
            )
        )
    ).scalars()
    mapping: dict[int, PracticeSquad] = {entry.player_id: entry for entry in entries}
    missing = set(player_ids) - set(mapping)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Players {sorted(missing)} are not on the practice squad",
        )
    for entry in mapping.values():
        if entry.ps_ir:
            raise HTTPException(
                status_code=422,
                detail=f"Player {entry.player_id} is on practice squad IR",
            )
        if entry.elevations >= MAX_ELEVATIONS_PER_PLAYER:
            raise HTTPException(
                status_code=422,
                detail=f"Player {entry.player_id} exceeded elevation limit",
            )
    return mapping


def ensure_roster_totals(
    actives: Sequence[int], inactives: Sequence[int], elevations: Sequence[int]
) -> None:
    expected_total = BASE_ROSTER_LIMIT + len(elevations)
    total = len(actives) + len(inactives)
    if total != expected_total:
        raise HTTPException(
            status_code=422,
            detail=(
                "Total players (actives + inactives) must equal 53 plus elevated players. "
                f"Received {total}, expected {expected_total}."
            ),
        )


def ensure_elevation_limits(elevated_ids: Sequence[int]) -> None:
    if len(elevated_ids) > MAX_ELEVATIONS_PER_GAME:
        raise HTTPException(status_code=422, detail="Maximum 2 elevations per game")


def ensure_disjoint(actives: Sequence[int], inactives: Sequence[int]) -> None:
    overlap = set(actives) & set(inactives)
    if overlap:
        raise HTTPException(
            status_code=422,
            detail=f"Players cannot be both active and inactive: {sorted(overlap)}",
        )
