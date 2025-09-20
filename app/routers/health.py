from __future__ import annotations

from typing import Dict, List, Tuple

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Injury, Player, PlayerStamina, Team
from app.schemas import (
    InjuryDetail,
    InjuryListResponse,
    TeamHealthSummary,
    TeamHealthSummaryResponse,
)
from app.services.injuries import FATIGUE_THRESHOLD

router = APIRouter(prefix="/health", tags=["health"])


def _apply_common_filters(
    query,
    *,
    team_id: int | None,
    severity: str | None,
    active_only: bool,
):
    if team_id is not None:
        query = query.where(Injury.team_id == team_id)
    if severity:
        query = query.where(func.lower(Injury.severity) == severity.lower())
    if active_only:
        query = query.where(Injury.expected_weeks_out > 0)
    return query


@router.get(
    "/injuries",
    response_model=InjuryListResponse,
    summary="List recorded injuries",
    description=(
        "Return persisted injuries with optional filters for team, severity, and "
        "whether the player remains sidelined."
    ),
)
async def list_injuries(
    team_id: int | None = Query(default=None, description="Filter by team identifier."),
    severity: str | None = Query(
        default=None, description="Filter by severity bucket (case-insensitive)."
    ),
    active_only: bool = Query(
        default=True,
        description="When true, only injuries with remaining weeks-out are returned.",
    ),
    db: AsyncSession = Depends(get_db),
) -> InjuryListResponse:
    base_query = (
        select(Injury, Player, Team)
        .join(Player, Injury.player_id == Player.id)
        .join(Team, Injury.team_id == Team.id)
        .order_by(Injury.occurred_at.desc())
    )
    data_query = _apply_common_filters(
        base_query, team_id=team_id, severity=severity, active_only=active_only
    )
    result = await db.execute(data_query)
    items: List[InjuryDetail] = []
    for injury, player, team in result.all():
        items.append(
            InjuryDetail(
                id=injury.id,
                player_id=injury.player_id,
                player_name=player.name,
                team_id=injury.team_id,
                team_name=team.name,
                game_id=injury.game_id,
                injury_type=injury.type,
                severity=injury.severity,
                expected_weeks_out=injury.expected_weeks_out,
                occurred_at=injury.occurred_at,
            )
        )

    count_query = _apply_common_filters(
        select(func.count()).select_from(Injury),
        team_id=team_id,
        severity=severity,
        active_only=active_only,
    )
    total = await db.scalar(count_query)
    return InjuryListResponse(items=items, total=int(total or 0))


@router.get(
    "/summary",
    response_model=TeamHealthSummaryResponse,
    summary="Team health overview",
    description=(
        "Aggregate injuries and fatigue by team, highlighting severe cases and players "
        "carrying significant workloads."
    ),
)
async def team_health_summary(db: AsyncSession = Depends(get_db)) -> TeamHealthSummaryResponse:
    teams = {team.id: team for team in (await db.execute(select(Team))).scalars()}
    if not teams:
        return TeamHealthSummaryResponse(items=[])

    injury_stats = await db.execute(
        select(
            Injury.team_id,
            func.count(Injury.id).label("injury_count"),
            func.sum(case((Injury.expected_weeks_out >= 5, 1), else_=0)).label("severe_count"),
        )
        .where(Injury.expected_weeks_out > 0)
        .group_by(Injury.team_id)
    )
    injury_by_team: Dict[int, Tuple[int, int]] = {
        row.team_id: (row.injury_count or 0, row.severe_count or 0)  # type: ignore[misc]
        for row in injury_stats
        if row.team_id is not None
    }

    fatigue_stats = await db.execute(
        select(
            Player.team_id,
            func.avg(PlayerStamina.fatigue).label("avg_fatigue"),
            func.sum(case((PlayerStamina.fatigue >= FATIGUE_THRESHOLD, 1), else_=0)).label(
                "high_fatigue"
            ),
        )
        .join(Player, Player.id == PlayerStamina.player_id)
        .group_by(Player.team_id)
    )
    fatigue_by_team: Dict[int, Tuple[float | None, int]] = {}
    for row in fatigue_stats:
        if row.team_id is None:
            continue
        avg_value = float(row.avg_fatigue) if row.avg_fatigue is not None else None
        fatigue_by_team[row.team_id] = (avg_value, int(row.high_fatigue or 0))

    items: List[TeamHealthSummary] = []
    for team_id, team in teams.items():
        injuries = injury_by_team.get(team_id)
        fatigue = fatigue_by_team.get(team_id)
        if injuries is None and fatigue is None:
            continue
        active_injuries = injuries[0] if injuries else 0
        severe_injuries = injuries[1] if injuries else 0
        avg_fatigue = fatigue[0] if fatigue else None
        high_fatigue = fatigue[1] if fatigue else 0
        items.append(
            TeamHealthSummary(
                team_id=team_id,
                team_name=team.name,
                active_injuries=active_injuries,
                severe_injuries=severe_injuries,
                average_fatigue=avg_fatigue,
                high_fatigue_players=high_fatigue,
            )
        )

    items.sort(key=lambda summary: (-summary.active_injuries, -summary.severe_injuries))
    return TeamHealthSummaryResponse(items=items)
