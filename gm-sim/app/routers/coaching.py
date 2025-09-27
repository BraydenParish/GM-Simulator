"""Endpoints for managing coaching staffs and scheme fits."""

from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Coach, CoachAssignment, Team
from app.schemas import (
    CoachAssignmentRead,
    CoachCreate,
    CoachEffectRead,
    CoachHireRequest,
    CoachRead,
    TeamCoachingOverview,
)
from app.services.coaching import CoachingSystem

router = APIRouter(prefix="/coaching", tags=["coaching"])


@router.get("/coaches", response_model=List[CoachRead])
async def list_coaches(db: AsyncSession = Depends(get_db)) -> List[CoachRead]:
    result = await db.execute(select(Coach).order_by(Coach.name))
    return [CoachRead.model_validate(row) for row in result.scalars().all()]


@router.post("/coaches", response_model=CoachRead, status_code=201)
async def create_coach(payload: CoachCreate, db: AsyncSession = Depends(get_db)) -> CoachRead:
    coach = Coach(**payload.model_dump())
    db.add(coach)
    await db.commit()
    await db.refresh(coach)
    return CoachRead.model_validate(coach)


async def _assignment_rows(db: AsyncSession, team_id: int) -> List[tuple[CoachAssignment, Coach]]:
    query: Select = (
        select(CoachAssignment, Coach)
        .join(Coach, CoachAssignment.coach_id == Coach.id)
        .where(CoachAssignment.team_id == team_id, CoachAssignment.active.is_(True))
        .order_by(CoachAssignment.role)
    )
    result = await db.execute(query)
    return list(result.all())


@router.get("/teams/{team_id}", response_model=TeamCoachingOverview)
async def team_coaching_overview(team_id: int, db: AsyncSession = Depends(get_db)) -> TeamCoachingOverview:
    team = await db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    assignments = []
    rows = await _assignment_rows(db, team_id)
    for assignment, coach in rows:
        assignments.append(
            CoachAssignmentRead(
                id=assignment.id,
                coach_id=coach.id,
                coach_name=coach.name,
                team_id=team_id,
                role=assignment.role,
                hired_at=assignment.hired_at,
                contract_years=assignment.contract_years,
                salary=assignment.salary,
                interim=assignment.interim,
                active=assignment.active,
                scheme=coach.scheme,
            )
        )

    system = await CoachingSystem.build(db)
    effect = system.effect_for(team_id)

    return TeamCoachingOverview(
        team_id=team_id,
        team_name=team.name,
        assignments=assignments,
        effect=CoachEffectRead(**effect.to_dict()),
    )


@router.post("/coaches/{coach_id}/hire", response_model=CoachAssignmentRead)
async def hire_coach(
    coach_id: int,
    payload: CoachHireRequest,
    db: AsyncSession = Depends(get_db),
) -> CoachAssignmentRead:
    coach = await db.get(Coach, coach_id)
    if coach is None:
        raise HTTPException(status_code=404, detail="Coach not found")
    team = await db.get(Team, payload.team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    # Deactivate any existing coach in the same role
    await db.execute(
        update(CoachAssignment)
        .where(
            CoachAssignment.team_id == payload.team_id,
            CoachAssignment.role == payload.role,
            CoachAssignment.active.is_(True),
        )
        .values(active=False)
    )

    assignment = CoachAssignment(
        coach_id=coach_id,
        team_id=payload.team_id,
        role=payload.role,
        contract_years=payload.contract_years,
        salary=payload.salary,
        interim=payload.interim,
        active=True,
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)

    return CoachAssignmentRead(
        id=assignment.id,
        coach_id=coach_id,
        coach_name=coach.name,
        team_id=payload.team_id,
        role=payload.role,
        hired_at=assignment.hired_at,
        contract_years=assignment.contract_years,
        salary=assignment.salary,
        interim=assignment.interim,
        active=assignment.active,
        scheme=coach.scheme,
    )


@router.post("/coaches/{coach_id}/fire", response_model=Dict[str, int])
async def fire_coach(coach_id: int, db: AsyncSession = Depends(get_db)) -> Dict[str, int]:
    assignment = (
        await db.execute(
            select(CoachAssignment)
            .where(CoachAssignment.coach_id == coach_id, CoachAssignment.active.is_(True))
            .limit(1)
        )
    ).scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Active assignment not found")

    assignment.active = False
    await db.commit()
    return {"assignment_id": assignment.id}
