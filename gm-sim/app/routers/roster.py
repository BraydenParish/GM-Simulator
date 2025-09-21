from typing import Dict, Iterable, Sequence, Set

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import GamedayRoster, PracticeSquad, Player
from app.schemas import (
    ErrorResponse,
    GamedayRosterRead,
    GamedaySetActivesRequest,
    PracticeSquadAssignRequest,
    PracticeSquadRead,
)

router = APIRouter(prefix="/roster", tags=["roster"])

OL_POSITIONS: Set[str] = {"C", "G", "LG", "RG", "LT", "RT", "OG", "OT", "OL"}
MAX_PRACTICE_SQUAD = 16
MAX_IPP_SLOTS = 1
MAX_ELEVATIONS_PER_GAME = 2
MAX_ELEVATIONS_PER_PLAYER = 3
ROSTER_LIMIT = 53


def _normalize_position(value: str | None) -> str:
    return (value or "").strip().upper()


@router.post(
    "/practice-squad/assign",
    response_model=PracticeSquadRead,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def assign_practice_squad(
    payload: PracticeSquadAssignRequest, db: AsyncSession = Depends(get_db)
) -> PracticeSquadRead:
    player = await db.get(Player, payload.player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    existing_entry = await db.execute(
        select(PracticeSquad).where(PracticeSquad.player_id == payload.player_id)
    )
    if existing_entry.scalar_one_or_none() is not None:
        raise HTTPException(status_code=422, detail="Player already on practice squad")

    regular_count = await db.scalar(
        select(func.count()).where(
            PracticeSquad.team_id == payload.team_id,
            PracticeSquad.international_pathway.is_(False),
        )
    )
    if not payload.international_pathway and regular_count >= MAX_PRACTICE_SQUAD:
        raise HTTPException(
            status_code=422, detail="Practice squad is full (16 players)"
        )

    if payload.international_pathway:
        ipp_count = await db.scalar(
            select(func.count()).where(
                PracticeSquad.team_id == payload.team_id,
                PracticeSquad.international_pathway.is_(True),
            )
        )
        if ipp_count >= MAX_IPP_SLOTS:
            raise HTTPException(
                status_code=422, detail="International Pathway slot already in use"
            )

    if player.team_id is None:
        player.team_id = payload.team_id
    elif player.team_id != payload.team_id:
        raise HTTPException(status_code=422, detail="Player belongs to another team")

    entry = PracticeSquad(
        team_id=payload.team_id,
        player_id=payload.player_id,
        international_pathway=payload.international_pathway,
        ps_ir=payload.ps_ir,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return PracticeSquadRead.model_validate(entry)


def _validate_roster_lists(actives: Sequence[int], inactives: Sequence[int]) -> None:
    unique_players = set(actives) | set(inactives)
    if len(unique_players) != len(actives) + len(inactives):
        raise HTTPException(
            status_code=422, detail="Duplicate player IDs in roster submission"
        )
    if len(unique_players) != ROSTER_LIMIT:
        raise HTTPException(
            status_code=422, detail="Gameday roster must include 53 players"
        )


async def _fetch_players(
    db: AsyncSession, player_ids: Iterable[int]
) -> Dict[int, Player]:
    result = await db.execute(select(Player).where(Player.id.in_(set(player_ids))))
    players = result.scalars().all()
    players_by_id = {player.id: player for player in players}
    if len(players_by_id) != len(set(player_ids)):
        raise HTTPException(
            status_code=422, detail="Roster submission references unknown players"
        )
    return players_by_id


def _validate_actives_against_rules(
    actives: Sequence[int], players_by_id: Dict[int, Player]
) -> int:
    ol_count = sum(
        1
        for player_id in actives
        if _normalize_position(players_by_id[player_id].pos) in OL_POSITIONS
    )
    required_actives = 48 if ol_count >= 8 else 47
    if len(actives) != required_actives:
        raise HTTPException(
            status_code=422,
            detail=f"Team must dress {required_actives} players based on offensive line count",
        )
    return ol_count


def _validate_team_affiliation(
    team_id: int, players: Dict[int, Player], roster_player_ids: Iterable[int]
) -> None:
    for player_id in roster_player_ids:
        player = players[player_id]
        if player.team_id != team_id:
            raise HTTPException(
                status_code=422,
                detail=f"Player {player_id} does not belong to team {team_id}",
            )


@router.post(
    "/gameday/set-actives",
    response_model=GamedayRosterRead,
    responses={422: {"model": ErrorResponse}},
)
async def set_gameday_actives(
    payload: GamedaySetActivesRequest, db: AsyncSession = Depends(get_db)
) -> GamedayRosterRead:
    _validate_roster_lists(payload.actives, payload.inactives)
    players_by_id = await _fetch_players(db, payload.actives + payload.inactives)
    _validate_team_affiliation(
        payload.team_id, players_by_id, payload.actives + payload.inactives
    )
    ol_count = _validate_actives_against_rules(payload.actives, players_by_id)

    requested_elevations = list(dict.fromkeys(payload.elevated_player_ids))
    if len(requested_elevations) > MAX_ELEVATIONS_PER_GAME:
        raise HTTPException(
            status_code=422, detail="Maximum of two elevations per game"
        )

    active_set = set(payload.actives)
    if not set(requested_elevations).issubset(active_set):
        raise HTTPException(
            status_code=422,
            detail="Elevated practice-squad players must appear on the actives list",
        )

    roster_stmt = select(GamedayRoster).where(
        GamedayRoster.game_id == payload.game_id,
        GamedayRoster.team_id == payload.team_id,
    )
    existing_roster = (await db.execute(roster_stmt)).scalar_one_or_none()
    previous_elevations: Set[int] = (
        set(existing_roster.elevated_player_ids or []) if existing_roster else set()
    )

    practice_entries: Dict[int, PracticeSquad] = {}
    if requested_elevations:
        practice_stmt = select(PracticeSquad).where(
            PracticeSquad.player_id.in_(requested_elevations),
            PracticeSquad.team_id == payload.team_id,
        )
        practice_entries = {
            entry.player_id: entry
            for entry in (await db.execute(practice_stmt)).scalars()
        }
        if len(practice_entries) != len(requested_elevations):
            raise HTTPException(
                status_code=422, detail="Elevated player is not on the practice squad"
            )

        for player_id in requested_elevations:
            if player_id not in previous_elevations:
                entry = practice_entries[player_id]
                if entry.elevations >= MAX_ELEVATIONS_PER_PLAYER:
                    raise HTTPException(
                        status_code=422,
                        detail="Player has reached the maximum of three elevations",
                    )
                entry.elevations += 1

    if existing_roster is None:
        gameday_roster = GamedayRoster(
            game_id=payload.game_id,
            team_id=payload.team_id,
            actives=list(payload.actives),
            inactives=list(payload.inactives),
            elevated_player_ids=requested_elevations,
            ol_count=ol_count,
            valid=True,
        )
        db.add(gameday_roster)
    else:
        existing_roster.actives = list(payload.actives)
        existing_roster.inactives = list(payload.inactives)
        existing_roster.elevated_player_ids = requested_elevations
        existing_roster.ol_count = ol_count
        existing_roster.valid = True
        gameday_roster = existing_roster

    await db.commit()
    await db.refresh(gameday_roster)
    return GamedayRosterRead.model_validate(gameday_roster)
