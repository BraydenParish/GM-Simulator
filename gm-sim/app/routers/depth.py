from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.db import get_db
from app.models import DepthChart
from app.schemas import DepthChartRead, DepthChartCreate
from typing import List

router = APIRouter(prefix="/depth", tags=["depth"])

@router.get("/{team_id}", response_model=List[DepthChartRead])
async def get_depth(team_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DepthChart).where(DepthChart.team_id == team_id))
    return result.scalars().all()

@router.put("/{team_id}", response_model=List[DepthChartRead])
async def set_depth(team_id: int, slots: List[DepthChartCreate], db: AsyncSession = Depends(get_db)):
    # Remove old
    await db.execute(delete(DepthChart).where(DepthChart.team_id == team_id))
    # Add new
    for slot in slots:
        db.add(DepthChart(**slot.model_dump()))
    await db.commit()
    result = await db.execute(select(DepthChart).where(DepthChart.team_id == team_id))
    return result.scalars().all()
