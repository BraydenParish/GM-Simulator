from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import GamedayRoster, PracticeSquad
from app.schemas import (
    ErrorResponse,
    GamedayRosterRead,
    GamedayRosterSetRequest,
    PracticeSquadAssignRequest,
    PracticeSquadEntryRead,
)
from app.services.roster_rules import (
    compute_required_actives,
    count_offensive_line,
    ensure_disjoint,
    ensure_elevation_limits,
    ensure_no_existing_gameday,
    ensure_practice_squad_capacity,
    ensure_practice_squad_entry_unique,
    ensure_roster_totals,
    ensure_unique_ids,
    fetch_practice_squad_entries,
    fetch_team_players,
)

router = APIRouter(prefix="/roster", tags=["roster"])


@router.post(
    "/practice-squad/assign",
    response_model=PracticeSquadEntryRead,
    summary="Assign a player to the practice squad",
    responses={
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def assign_practice_squad(
    payload: PracticeSquadAssignRequest, db: AsyncSession = Depends(get_db)
) -> PracticeSquadEntryRead:
    await ensure_practice_squad_entry_unique(db, payload.player_id)
    await ensure_practice_squad_capacity(db, payload.team_id, payload.international_pathway)
    await fetch_team_players(db, payload.team_id, [payload.player_id])

    entry = PracticeSquad(**payload.model_dump())
    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    return PracticeSquadEntryRead.model_validate(entry)


@router.post(
    "/gameday/set-actives",
    response_model=GamedayRosterRead,
    summary="Submit gameday actives and inactives",
    responses={
        200: {
            "description": "Roster accepted",
        },
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def set_gameday_actives(
    request: GamedayRosterSetRequest, db: AsyncSession = Depends(get_db)
) -> GamedayRosterRead:
    ensure_unique_ids(request.actives, "actives")
    ensure_unique_ids(request.inactives, "inactives")
    ensure_unique_ids(request.elevated_player_ids, "elevated_player_ids")
    ensure_disjoint(request.actives, request.inactives)
    ensure_roster_totals(request.actives, request.inactives, request.elevated_player_ids)
    ensure_elevation_limits(request.elevated_player_ids)

    await ensure_no_existing_gameday(db, request.team_id, request.game_id)

    active_players = await fetch_team_players(db, request.team_id, request.actives)
    await fetch_team_players(db, request.team_id, request.inactives)

    ol_count = count_offensive_line(active_players)
    required_actives = compute_required_actives(ol_count)
    if len(request.actives) != required_actives:
        raise HTTPException(
            status_code=422,
            detail=(
                "Teams must declare 48 actives when dressing at least eight offensive linemen "
                "and 47 otherwise."
            ),
        )

    practice_entries = await fetch_practice_squad_entries(
        db, request.team_id, request.elevated_player_ids
    )

    for player_id in request.elevated_player_ids:
        if player_id not in request.actives:
            raise HTTPException(
                status_code=422,
                detail=f"Elevated player {player_id} must be on the active list",
            )

    for entry in practice_entries.values():
        entry.elevations += 1

    roster = GamedayRoster(
        game_id=request.game_id,
        team_id=request.team_id,
        actives=request.actives,
        inactives=request.inactives,
        elevated_player_ids=request.elevated_player_ids,
        ol_count=ol_count,
        valid=True,
    )
    db.add(roster)
    await db.commit()
    await db.refresh(roster)

    return GamedayRosterRead.model_validate(roster)
