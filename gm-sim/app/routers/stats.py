from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import PlayerGameStat, PlayerSeasonStat, TeamSeasonStat
from app.schemas import (
    PlayerGameStatRead,
    PlayerSeasonStatRead,
    TeamSeasonStatRead,
)

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/players/game", response_model=List[PlayerGameStatRead])
async def list_player_game_stats(
    game_id: int,
    team_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
) -> List[PlayerGameStatRead]:
    query = select(PlayerGameStat).where(PlayerGameStat.game_id == game_id)
    if team_id is not None:
        query = query.where(PlayerGameStat.team_id == team_id)
    result = await db.execute(query.order_by(PlayerGameStat.id))
    return result.scalars().all()


@router.get("/players/season", response_model=List[PlayerSeasonStatRead])
async def list_player_season_stats(
    season: int,
    player_id: Optional[int] = None,
    team_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
) -> List[PlayerSeasonStatRead]:
    query = select(PlayerSeasonStat).where(PlayerSeasonStat.season == season)
    if player_id is not None:
        query = query.where(PlayerSeasonStat.player_id == player_id)
    if team_id is not None:
        query = query.where(PlayerSeasonStat.team_id == team_id)
    result = await db.execute(query.order_by(PlayerSeasonStat.player_id))
    return result.scalars().all()


@router.get("/teams/season", response_model=List[TeamSeasonStatRead])
async def list_team_season_stats(
    season: int,
    team_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
) -> List[TeamSeasonStatRead]:
    query = select(TeamSeasonStat).where(TeamSeasonStat.season == season)
    if team_id is not None:
        query = query.where(TeamSeasonStat.team_id == team_id)
    result = await db.execute(query.order_by(TeamSeasonStat.team_id))
    return result.scalars().all()
