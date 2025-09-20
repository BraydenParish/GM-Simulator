from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db import get_db
from app.models import DraftPick
from app.schemas import DraftPickRead
from typing import List

router = APIRouter(prefix="/picks", tags=["picks"])


@router.get("/", response_model=List[DraftPickRead])
async def list_picks(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DraftPick))
    return result.scalars().all()


@router.post("/{pick_id}/transfer", response_model=DraftPickRead)
async def transfer_pick(pick_id: int, new_team_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DraftPick).where(DraftPick.id == pick_id))
    pick = result.scalar_one_or_none()
    if not pick:
        raise HTTPException(status_code=404, detail="Pick not found")
    pick.owned_by_team_id = new_team_id
    await db.commit()
    await db.refresh(pick)
    return pick
