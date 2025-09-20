from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db import get_db
from app.models import Player
from app.schemas import PlayerRead, PlayerCreate
from typing import List

router = APIRouter(prefix="/players", tags=["players"])

@router.get("/", response_model=List[PlayerRead])
async def list_players(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Player))
    return result.scalars().all()

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
