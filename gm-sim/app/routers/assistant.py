from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db import get_db
from app.models import Game, Schedule, Standing, Team
from app.schemas import (
    FreeAgentBiddingRequest,
    FreeAgentBiddingResult,
    FreeAgentProjectionRead,
    FreeAgentSigningPlan,
    FreeAgentSigningResponse,
    FreeAgentSummary,
    GameHighlight,
    GameSummaryWithHighlights,
    SeasonDashboardResponse,
    SeasonProgressSummary,
    StandingSnapshot,
    UpcomingGameSummary,
)
from app.services.free_agency import (
    evaluate_free_agent_bidding,
    list_free_agents,
    project_free_agents,
    sign_free_agent,
)
from app.services.highlights import summarize_drives
from app.routers.seasons import _season_progress

router = APIRouter(prefix="/assistant", tags=["assistant"])


async def _team_lookup(db: AsyncSession, team_id: int) -> Team | None:
    return await db.get(Team, team_id)


def _extract_drives(box_json: Any) -> List[Dict[str, Any]]:
    if isinstance(box_json, dict):
        drives = box_json.get("drives")
        if isinstance(drives, list):
            return drives
    if isinstance(box_json, list):
        return box_json
    return []


@router.get("/free-agents/projections", response_model=List[FreeAgentProjectionRead])
async def assistant_free_agent_projections(
    season: int,
    limit: Optional[int] = 10,
    db: AsyncSession = Depends(get_db),
) -> List[FreeAgentProjectionRead]:
    return await project_free_agents(db, season, limit=limit)


@router.get("/free-agents/pool", response_model=List[FreeAgentSummary])
async def assistant_free_agent_pool(
    limit: Optional[int] = 25,
    db: AsyncSession = Depends(get_db),
) -> List[FreeAgentSummary]:
    return await list_free_agents(db, limit=limit)


@router.post("/free-agents/sign", response_model=FreeAgentSigningResponse)
async def assistant_sign_free_agent(
    payload: FreeAgentSigningPlan,
    db: AsyncSession = Depends(get_db),
) -> FreeAgentSigningResponse:
    return await sign_free_agent(db, payload)


@router.post("/free-agents/bid", response_model=FreeAgentBiddingResult)
async def assistant_free_agent_bidding(
    payload: FreeAgentBiddingRequest,
    db: AsyncSession = Depends(get_db),
) -> FreeAgentBiddingResult:
    return await evaluate_free_agent_bidding(db, payload)


@router.get("/games/{game_id}/highlights", response_model=GameSummaryWithHighlights)
async def assistant_game_highlights(
    game_id: int,
    db: AsyncSession = Depends(get_db),
) -> GameSummaryWithHighlights:
    game = await db.get(Game, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    home_team = await _team_lookup(db, game.home_team_id)
    away_team = await _team_lookup(db, game.away_team_id)
    drives = _extract_drives(game.box_json)
    highlights = [
        GameHighlight(
            game_id=game.id,
            drive_index=entry["drive_index"],
            descriptor=entry.get("descriptor", "highlight"),
            team=entry.get("team"),
            result=entry.get("result"),
            yards=entry.get("yards"),
            clock_minutes=entry.get("clock_minutes"),
        )
        for entry in summarize_drives(drives)
    ]
    return GameSummaryWithHighlights(
        game_id=game.id,
        season=game.season,
        week=game.week,
        home_team_id=game.home_team_id,
        away_team_id=game.away_team_id,
        home_team=home_team.name if home_team else "Home",
        away_team=away_team.name if away_team else "Away",
        home_score=game.home_score,
        away_score=game.away_score,
        narrative_recap=game.narrative_recap,
        highlights=highlights,
    )


@router.get("/season-dashboard", response_model=SeasonDashboardResponse)
async def assistant_season_dashboard(
    season: int,
    projection_year: Optional[int] = None,
    free_agent_limit: int = 10,
    db: AsyncSession = Depends(get_db),
) -> SeasonDashboardResponse:
    progress_data = await _season_progress(db, season)
    progress = SeasonProgressSummary(**progress_data)

    standings_rows = await db.execute(
        select(Standing, Team)
        .join(Team, Standing.team_id == Team.id)
        .where(Standing.season == season)
        .order_by(Standing.wins.desc(), Standing.pf.desc())
    )
    standings = [
        StandingSnapshot(
            team_id=standing.team_id,
            team_name=team.name,
            team_abbr=team.abbr,
            wins=standing.wins,
            losses=standing.losses,
            ties=standing.ties,
            points_for=standing.pf,
            points_against=standing.pa,
            elo=standing.elo,
        )
        for standing, team in standings_rows.all()
    ]

    upcoming: List[UpcomingGameSummary] = []
    if progress.next_week is not None:
        HomeTeam = aliased(Team)
        AwayTeam = aliased(Team)
        upcoming_rows = await db.execute(
            select(Schedule, HomeTeam, AwayTeam)
            .join(HomeTeam, Schedule.home_team_id == HomeTeam.id)
            .join(AwayTeam, Schedule.away_team_id == AwayTeam.id)
            .where(Schedule.season == season, Schedule.week == progress.next_week)
            .order_by(Schedule.id)
        )
        for schedule, home, away in upcoming_rows.all():
            upcoming.append(
                UpcomingGameSummary(
                    game_id=schedule.id,
                    week=schedule.week,
                    home_team_id=schedule.home_team_id,
                    away_team_id=schedule.away_team_id,
                    home_team=home.name,
                    away_team=away.name,
                )
            )

    recent_games: List[GameSummaryWithHighlights] = []
    if progress.last_completed_week is not None:
        HomeTeam = aliased(Team)
        AwayTeam = aliased(Team)
        recent_rows = await db.execute(
            select(Game, HomeTeam, AwayTeam)
            .join(HomeTeam, Game.home_team_id == HomeTeam.id)
            .join(AwayTeam, Game.away_team_id == AwayTeam.id)
            .where(Game.season == season, Game.week == progress.last_completed_week)
            .order_by(Game.id)
        )
        for game, home, away in recent_rows.all():
            highlights = [
                GameHighlight(
                    game_id=game.id,
                    drive_index=entry["drive_index"],
                    descriptor=entry.get("descriptor", "highlight"),
                    team=entry.get("team"),
                    result=entry.get("result"),
                    yards=entry.get("yards"),
                    clock_minutes=entry.get("clock_minutes"),
                )
                for entry in summarize_drives(_extract_drives(game.box_json))
            ]
            recent_games.append(
                GameSummaryWithHighlights(
                    game_id=game.id,
                    season=game.season,
                    week=game.week,
                    home_team_id=game.home_team_id,
                    away_team_id=game.away_team_id,
                    home_team=home.name,
                    away_team=away.name,
                    home_score=game.home_score,
                    away_score=game.away_score,
                    narrative_recap=game.narrative_recap,
                    highlights=highlights,
                )
            )

    projection_target = projection_year or (season + 1 if not progress.season_over else season)
    projections = await project_free_agents(db, projection_target, limit=free_agent_limit)
    free_agent_pool = await list_free_agents(db, limit=free_agent_limit)

    return SeasonDashboardResponse(
        progress=progress,
        upcoming_games=upcoming,
        standings=standings,
        recent_games=recent_games,
        free_agent_targets=projections,
        available_free_agents=free_agent_pool,
    )
