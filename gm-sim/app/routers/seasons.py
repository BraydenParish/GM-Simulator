from collections import defaultdict
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Game, InjuryReport, Schedule, Standing, Team
from app.schemas import GameRead, StandingRead
from app.services.injuries import InjuryEngine
from app.services.llm import OpenRouterClient
from app.services.season import SeasonSimulator, TeamSeed
from app.services.state import GameStateStore

router = APIRouter(prefix="/seasons", tags=["seasons"])


@router.get("/debug-config")
async def debug_configuration():
    """Debug endpoint to check system configuration."""
    import os
    
    config_status = {
        "openrouter_api_key_configured": bool(os.getenv("OPENROUTER_API_KEY")),
        "openrouter_api_key_length": len(os.getenv("OPENROUTER_API_KEY", "")),
        "available_services": {
            "narrative_generation": bool(os.getenv("OPENROUTER_API_KEY")),
            "injury_simulation": True,  # Always available
            "season_simulation": True,  # Always available
        }
    }
    
    return config_status


@router.post("/simulate-full")
async def simulate_full_season(
    season: int,
    generate_narratives: bool = True,
    use_injuries: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """Simulate an entire season for all teams."""
    
    try:
        # Get all teams
        teams_result = await db.execute(select(Team))
        teams = list(teams_result.scalars())

        if not teams:
            raise HTTPException(status_code=404, detail="No teams found")
        
        # Build team seeds from database
        team_seeds = [
            TeamSeed(
                id=team.id,
                name=team.name,
                abbr=team.abbr,
                rating=team.elo or 1500
            )
            for team in teams
        ]
        
        # Set up services with error handling
        narrative_client = None
        if generate_narratives:
            try:
                narrative_client = OpenRouterClient()
                # Test if API key is configured
                if not narrative_client.api_key:
                    raise HTTPException(
                        status_code=400, 
                        detail="OpenRouter API key not configured. Set OPENROUTER_API_KEY environment variable."
                    )
            except RuntimeError as e:
                raise HTTPException(status_code=400, detail=f"Narrative setup failed: {str(e)}")
        
        injury_engine = InjuryEngine() if use_injuries else None
        state_store = GameStateStore(db)
        rosters = None
        if injury_engine is not None:
            rosters = await state_store.participant_rosters()

        # Create simulator
        simulator = SeasonSimulator(
            team_seeds,
            narrative_client=narrative_client,
            injury_engine=injury_engine,
            rosters=rosters,
            state_store=state_store,
            season_year=season,
        )
        
        # Clear prior injury reports for this season to avoid duplication
        await db.execute(delete(InjuryReport).where(InjuryReport.season == season))

        # Run simulation
        game_logs = await simulator.simulate_season()
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Catch any other unexpected errors
        import logging
        logging.error(f"Season simulation failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Season simulation failed: {str(e)}"
        )
    
    # Save games to database
    for log in game_logs:
        injury_records: Dict[int, Dict[str, object]] = {}
        for event in log.injuries:
            payload = event.to_dict(current_week=log.week, season=season)
            if payload["player_id"] is None:
                continue
            injury_records[int(payload["player_id"])] = payload

        injuries_payload = list(injury_records.values())
        analytics_payload = log.analytics or {}
        game = Game(
            season=season,
            week=log.week,
            home_team_id=log.home_team_id,
            away_team_id=log.away_team_id,
            home_score=log.home_score,
            away_score=log.away_score,
            sim_seed=None,
            box_json={"drives": log.drives, "analytics": analytics_payload},
            injuries_json=injuries_payload,
            narrative_recap=log.recap,
            narrative_facts=log.narrative_facts,
        )
        db.add(game)

        for payload in injuries_payload:
            occurred_snap = payload.get("occurred_snap")
            db.add(
                InjuryReport(
                    season=season,
                    week=log.week,
                    team_id=int(payload["team_id"]),
                    player_id=int(payload["player_id"]),
                    severity=str(payload["severity"]),
                    weeks_out=int(payload["weeks_out"]),
                    occurred_snap=int(occurred_snap) if occurred_snap is not None else None,
                    injury_type=str(payload["injury_type"]),
                    expected_return_week=payload.get("expected_return_week"),
                )
            )
    
    # Update standings
    standings_data = simulator.standings()
    for team_id, standing in standings_data.items():
        db_standing = (
            await db.execute(
                select(Standing).where(Standing.season == season, Standing.team_id == team_id)
            )
        ).scalar_one_or_none()
        
        if not db_standing:
            team = next(t for t in teams if t.id == team_id)
            db_standing = Standing(
                season=season,
                team_id=team_id,
                wins=0,
                losses=0,
                ties=0,
                pf=0,
                pa=0,
                elo=team.elo,
            )
            db.add(db_standing)
        
        db_standing.wins = standing.wins
        db_standing.losses = standing.losses
        db_standing.ties = standing.ties
        db_standing.pf = standing.points_for
        db_standing.pa = standing.points_against
    
    await db.commit()
    
    return {
        "season": season,
        "games_simulated": len(game_logs),
        "teams": len(team_seeds),
        "narratives_generated": generate_narratives,
        "injuries_simulated": use_injuries,
    }


@router.post("/simulate-week")
async def simulate_week(
    season: int,
    week: int,
    generate_narratives: bool = True,
    use_injuries: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Simulate a specific week of games."""
    
    # Get schedule for this week
    schedule_result = await db.execute(
        select(Schedule).where(Schedule.season == season, Schedule.week == week)
    )
    schedule_games = list(schedule_result.scalars())
    
    if not schedule_games:
        raise HTTPException(status_code=404, detail=f"No schedule found for season {season}, week {week}")
    
    await db.execute(
        delete(InjuryReport).where(
            InjuryReport.season == season, InjuryReport.week == week
        )
    )

    games_created = []
    state_store = GameStateStore(db)

    for scheduled_game in schedule_games:
        # Get teams
        home_team = (await db.execute(select(Team).where(Team.id == scheduled_game.home_team_id))).scalar_one_or_none()
        away_team = (await db.execute(select(Team).where(Team.id == scheduled_game.away_team_id))).scalar_one_or_none()
        
        if not home_team or not away_team:
            continue
        
        # Create team seeds
        team_seeds = [
            TeamSeed(id=home_team.id, name=home_team.name, abbr=home_team.abbr, rating=home_team.elo or 1500),
            TeamSeed(id=away_team.id, name=away_team.name, abbr=away_team.abbr, rating=away_team.elo or 1500),
        ]
        
        # Set up simulator for just these two teams
        narrative_client = OpenRouterClient() if generate_narratives else None
        injury_engine = None
        rosters = None
        if use_injuries:
            injury_engine = InjuryEngine()
            rosters = await state_store.participant_rosters()

        simulator = SeasonSimulator(
            team_seeds,
            narrative_client=narrative_client,
            injury_engine=injury_engine,
            rosters=rosters,
            state_store=state_store,
            season_year=season,
        )
        
        # Simulate just this matchup
        matchups = [(home_team.id, away_team.id)]
        await simulator.simulate_week(week, matchups)
        
        # Get the game result
        game_logs = simulator.games()
        if game_logs:
            log = game_logs[0]
            injury_records: Dict[int, Dict[str, object]] = {}
            for event in log.injuries:
                payload = event.to_dict(current_week=week, season=season)
                if payload["player_id"] is None:
                    continue
                injury_records[int(payload["player_id"])] = payload

            injuries_payload = list(injury_records.values())

            analytics_payload = log.analytics or {}
            game = Game(
                season=season,
                week=week,
                home_team_id=log.home_team_id,
                away_team_id=log.away_team_id,
                home_score=log.home_score,
                away_score=log.away_score,
                sim_seed=None,
                box_json={"drives": log.drives, "analytics": analytics_payload},
                injuries_json=injuries_payload,
                narrative_recap=log.recap,
                narrative_facts=log.narrative_facts,
            )
            db.add(game)
            games_created.append(game)

            for payload in injuries_payload:
                occurred_snap = payload.get("occurred_snap")
                db.add(
                    InjuryReport(
                        season=season,
                        week=week,
                        team_id=int(payload["team_id"]),
                        player_id=int(payload["player_id"]),
                        severity=str(payload["severity"]),
                        weeks_out=int(payload["weeks_out"]),
                        occurred_snap=int(occurred_snap)
                        if occurred_snap is not None
                        else None,
                        injury_type=str(payload["injury_type"]),
                        expected_return_week=payload.get("expected_return_week"),
                    )
                )
            
            # Update standings
            standings_data = simulator.standings()
            for team_id, standing in standings_data.items():
                db_standing = (
                    await db.execute(
                        select(Standing).where(Standing.season == season, Standing.team_id == team_id)
                    )
                ).scalar_one_or_none()
                
                if not db_standing:
                    team = home_team if team_id == home_team.id else away_team
                    db_standing = Standing(
                        season=season,
                        team_id=team_id,
                        wins=0,
                        losses=0,
                        ties=0,
                        pf=0,
                        pa=0,
                        elo=team.elo,
                    )
                    db.add(db_standing)
                
                # Add to existing record
                db_standing.wins += standing.wins
                db_standing.losses += standing.losses
                db_standing.ties += standing.ties
                db_standing.pf += standing.points_for
                db_standing.pa += standing.points_against
    
    await db.commit()
    
    return {
        "season": season,
        "week": week,
        "games_simulated": len(games_created),
        "narratives_generated": generate_narratives,
    }


async def _team_seeds(db: AsyncSession) -> List[TeamSeed]:
    teams_result = await db.execute(select(Team))
    teams = list(teams_result.scalars())
    if not teams:
        raise HTTPException(status_code=404, detail="No teams found")
    return [
        TeamSeed(
            id=team.id,
            name=team.name,
            abbr=team.abbr,
            rating=team.elo or 1500,
        )
        for team in teams
    ]


async def _generate_schedule(
    db: AsyncSession,
    *,
    season: int,
    weeks: int,
    replace_existing: bool,
) -> Dict[str, int]:
    if weeks < 1:
        raise HTTPException(status_code=400, detail="Weeks must be at least 1")

    if replace_existing:
        await db.execute(delete(Schedule).where(Schedule.season == season))
    else:
        existing = await db.scalar(
            select(func.count()).select_from(Schedule).where(Schedule.season == season)
        )
        if existing:
            return {"weeks_scheduled": weeks, "total_games": 0}

    team_seeds = await _team_seeds(db)
    simulator = SeasonSimulator(team_seeds, season_year=season)

    scheduled_weeks = min(weeks, len(simulator.schedule))
    created_games = 0
    for week_num, matchups in enumerate(simulator.schedule, start=1):
        if week_num > weeks:
            break
        for home_id, away_id in matchups:
            db.add(
                Schedule(
                    season=season,
                    week=week_num,
                    home_team_id=home_id,
                    away_team_id=away_id,
                    game_time=None,
                )
            )
            created_games += 1

    await db.commit()
    return {"weeks_scheduled": scheduled_weeks, "total_games": created_games}


async def _season_progress(db: AsyncSession, season: int) -> Dict[str, Optional[int] | int | bool]:
    schedule_rows = await db.execute(
        select(Schedule.week, func.count())
        .where(Schedule.season == season)
        .group_by(Schedule.week)
    )
    schedule_counts = {week: count for week, count in schedule_rows}

    if not schedule_counts:
        return {
            "season": season,
            "scheduled_weeks": 0,
            "scheduled_games": 0,
            "games_played": 0,
            "completed_weeks": 0,
            "next_week": None,
            "last_completed_week": None,
            "season_over": False,
        }

    game_rows = await db.execute(
        select(Game.week, func.count())
        .where(Game.season == season)
        .group_by(Game.week)
    )
    games_counts = defaultdict(int, {week: count for week, count in game_rows})

    total_games = sum(schedule_counts.values())
    games_played = sum(min(games_counts[week], schedule_counts[week]) for week in schedule_counts)

    completed_weeks = 0
    last_completed_week: Optional[int] = None
    next_week: Optional[int] = None
    for week in sorted(schedule_counts):
        scheduled = schedule_counts[week]
        played = games_counts[week]
        if played >= scheduled and scheduled > 0:
            completed_weeks += 1
            last_completed_week = week
        elif next_week is None:
            next_week = week

    season_over = next_week is None

    return {
        "season": season,
        "scheduled_weeks": len(schedule_counts),
        "scheduled_games": total_games,
        "games_played": games_played,
        "completed_weeks": completed_weeks,
        "next_week": next_week,
        "last_completed_week": last_completed_week,
        "season_over": season_over,
    }


@router.post("/generate-schedule")
async def generate_schedule(
    season: int,
    weeks: int = 18,
    db: AsyncSession = Depends(get_db),
):
    """Generate or replace the round-robin schedule for the season."""

    schedule_meta = await _generate_schedule(
        db, season=season, weeks=weeks, replace_existing=True
    )

    progress = await _season_progress(db, season)
    return {
        **schedule_meta,
        **progress,
    }


@router.post("/quickstart")
async def quickstart_season(
    season: int,
    weeks: int = 18,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Ensure a season has a schedule and return progress metadata for the UI."""

    created_schedule = False
    if force:
        await _generate_schedule(db, season=season, weeks=weeks, replace_existing=True)
        created_schedule = True
    else:
        existing = await db.scalar(
            select(func.count()).select_from(Schedule).where(Schedule.season == season)
        )
        if not existing:
            await _generate_schedule(db, season=season, weeks=weeks, replace_existing=True)
            created_schedule = True

    progress = await _season_progress(db, season)
    return {
        "season": season,
        "schedule_created": created_schedule,
        "weeks_requested": weeks,
        **progress,
    }


@router.get("/progress")
async def season_progress(
    season: int,
    db: AsyncSession = Depends(get_db),
):
    """Expose season progress metadata for the frontend."""

    return await _season_progress(db, season)


@router.get("/schedule")
async def get_schedule(
    season: int,
    week: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get the schedule for a season or specific week."""
    
    query = select(Schedule).where(Schedule.season == season)
    if week is not None:
        query = query.where(Schedule.week == week)
    
    schedule_result = await db.execute(query.order_by(Schedule.week, Schedule.id))
    schedule_games = list(schedule_result.scalars())
    
    return {
        "season": season,
        "week": week,
        "games": [
            {
                "id": game.id,
                "week": game.week,
                "home_team_id": game.home_team_id,
                "away_team_id": game.away_team_id,
                "game_time": game.game_time,
            }
            for game in schedule_games
        ]
    }


@router.get("/standings")
async def get_standings(
    season: int,
    db: AsyncSession = Depends(get_db),
):
    """Get current standings for a season."""
    
    standings_result = await db.execute(
        select(Standing)
        .where(Standing.season == season)
        .order_by(Standing.wins.desc(), Standing.pf.desc())
    )
    standings = list(standings_result.scalars())
    
    return {
        "season": season,
        "standings": [
            {
                "team_id": standing.team_id,
                "wins": standing.wins,
                "losses": standing.losses,
                "ties": standing.ties,
                "points_for": standing.pf,
                "points_against": standing.pa,
                "elo": standing.elo,
            }
            for standing in standings
        ]
    }
