from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.db import get_db
from app.models import Team
from app.schemas import TeamRead, TeamCreate
from typing import List

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("/", response_model=List[TeamRead])
async def list_teams(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Team))
    return result.scalars().all()


@router.post("/", response_model=TeamRead)
async def create_team(team_in: TeamCreate, db: AsyncSession = Depends(get_db)):
    # Check if team abbreviation already exists
    existing_result = await db.execute(select(Team).where(Team.abbr == team_in.abbr))
    existing_team = existing_result.scalar_one_or_none()
    if existing_team:
        raise HTTPException(
            status_code=409, 
            detail=f"Team abbreviation '{team_in.abbr}' already exists"
        )
    
    team = Team(**team_in.model_dump())
    db.add(team)
    await db.commit()
    await db.refresh(team)
    return team


@router.get("/{team_id}", response_model=TeamRead)
async def get_team(team_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


@router.put("/{team_id}", response_model=TeamRead)
async def update_team(team_id: int, team_in: TeamCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    for k, v in team_in.model_dump().items():
        setattr(team, k, v)
    await db.commit()
    await db.refresh(team)
    return team


@router.delete("/{team_id}")
async def delete_team(team_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    await db.delete(team)
    await db.commit()
    return {"message": "Team deleted successfully"}
