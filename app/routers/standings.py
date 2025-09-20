from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db import get_db
from app.models import Standing
from app.schemas import StandingRead
from typing import List

router = APIRouter(prefix="/standings", tags=["standings"])


@router.get("/{season}", response_model=List[StandingRead])
async def get_standings(season: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Standing).where(Standing.season == season))
    return result.scalars().all()
