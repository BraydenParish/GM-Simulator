from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Player
from app.schemas import (
    ErrorResponse,
    PlayerCreate,
    PlayerListResponse,
    PlayerRead,
)

router = APIRouter(prefix="/players", tags=["players"])

@router.get(
    "/",
    response_model=PlayerListResponse,
    responses={422: {"model": ErrorResponse}},
)
async def list_players(
    page: int = Query(1, ge=1, description="Page number (1-indexed)."),
    page_size: int = Query(
        25,
        ge=1,
        le=100,
        description="Number of players per page (max 100).",
    ),
    team_id: Optional[int] = Query(
        default=None, description="Filter players by current team ID."
    ),
    position: Optional[str] = Query(
        default=None, description="Filter players by position code."
    ),
    search: Optional[str] = Query(
        default=None,
        description="Case-insensitive search on player name substrings.",
    ),
    db: AsyncSession = Depends(get_db),
):
    filters = []
    if team_id is not None:
        filters.append(Player.team_id == team_id)
    if position:
        filters.append(func.lower(Player.pos) == position.lower())
    if search:
        filters.append(func.lower(Player.name).like(f"%{search.lower()}%"))

    query = select(Player).order_by(Player.id)
    if filters:
        query = query.where(*filters)

    total_query = select(func.count(Player.id))
    if filters:
        total_query = total_query.where(*filters)

    total_result = await db.execute(total_query)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    players = [PlayerRead.model_validate(player) for player in result.scalars().all()]

    return PlayerListResponse(
        items=players,
        total=total,
        page=page,
        page_size=page_size,
    )

@router.get("/{player_id}", response_model=PlayerRead)
async def get_player(player_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Player).where(Player.id == player_id))
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return player

@router.post("/", response_model=PlayerRead)
async def create_player(player_in: PlayerCreate, db: AsyncSession = Depends(get_db)):
    player = Player(**player_in.model_dump())
    db.add(player)
    await db.commit()
    await db.refresh(player)
    return player

@router.put("/{player_id}", response_model=PlayerRead)
async def update_player(player_id: int, player_in: PlayerCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Player).where(Player.id == player_id))
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    for k, v in player_in.model_dump().items():
        setattr(player, k, v)
    await db.commit()
    await db.refresh(player)
    return player

@router.post("/{player_id}/move", response_model=PlayerRead)
async def move_player(player_id: int, team_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Player).where(Player.id == player_id))
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    player.team_id = team_id
    await db.commit()
    await db.refresh(player)
    return player
