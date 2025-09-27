"""Endpoints for inspecting simulated injury reports."""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import InjuryReport, Player, Team
from app.schemas import InjuryReportList, InjuryReportRead

router = APIRouter(prefix="/injuries", tags=["injuries"])


@router.get("/report", response_model=InjuryReportList)
async def get_injury_report(
    season: int,
    week: int | None = None,
    team_id: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> InjuryReportList:
    """Return persisted injury reports for a given season filter."""

    query = (
        select(InjuryReport, Player.name, Team.abbr)
        .join(Player, InjuryReport.player_id == Player.id)
        .join(Team, InjuryReport.team_id == Team.id)
        .where(InjuryReport.season == season)
    )
    if week is not None:
        query = query.where(InjuryReport.week == week)
    if team_id is not None:
        query = query.where(InjuryReport.team_id == team_id)

    result = await db.execute(query.order_by(InjuryReport.week, Player.name))
    rows: List[tuple[InjuryReport, str, str]] = result.all()

    injuries: List[InjuryReportRead] = []
    for report, player_name, team_abbr in rows:
        injuries.append(
            InjuryReportRead(
                id=report.id,
                season=report.season,
                week=report.week,
                team_id=report.team_id,
                team_abbr=team_abbr,
                player_id=report.player_id,
                player_name=player_name,
                severity=report.severity,
                weeks_out=report.weeks_out,
                occurred_snap=report.occurred_snap,
                injury_type=report.injury_type,
                expected_return_week=report.expected_return_week,
            )
        )

    return InjuryReportList(
        season=season,
        week=week,
        team_id=team_id,
        injuries=injuries,
    )
