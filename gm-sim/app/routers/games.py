from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db import get_db
from app.models import Game, Standing, Team
from app.schemas import GameRead
from app.services.sim import simulate_game
from app.services.ratings import compute_team_rating
from typing import Dict

router = APIRouter(prefix="/games", tags=["games"])


@router.post("/simulate", response_model=GameRead)
async def simulate_game_endpoint(
    home_team_id: int,
    away_team_id: int,
    season: int,
    week: int,
    db: AsyncSession = Depends(get_db),
):
    # Get teams
    home_team = (await db.execute(select(Team).where(Team.id == home_team_id))).scalar_one_or_none()
    away_team = (await db.execute(select(Team).where(Team.id == away_team_id))).scalar_one_or_none()
    if not home_team or not away_team:
        raise HTTPException(status_code=404, detail="Team not found")
    # For MVP, use team elo as rating
    home_rating = home_team.elo
    away_rating = away_team.elo
    sim_result = simulate_game(home_team_id, away_team_id, home_rating, away_rating)
    game = Game(
        season=season,
        week=week,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_score=sim_result["home_score"],
        away_score=sim_result["away_score"],
        sim_seed=None,
        box_json=sim_result["box"],
        injuries_json=None,
    )
    db.add(game)
    await db.commit()
    await db.refresh(game)
    # Update standings (minimal)
    for team, score, opp_score in [
        (home_team, sim_result["home_score"], sim_result["away_score"]),
        (away_team, sim_result["away_score"], sim_result["home_score"]),
    ]:
        standing = (
            await db.execute(
                select(Standing).where(Standing.season == season, Standing.team_id == team.id)
            )
        ).scalar_one_or_none()
        if not standing:
            standing = Standing(
                season=season,
                team_id=team.id,
                wins=0,
                losses=0,
                ties=0,
                pf=0,
                pa=0,
                elo=team.elo,
            )
            db.add(standing)
        standing.pf += score
        standing.pa += opp_score
        if score > opp_score:
            standing.wins += 1
        elif score < opp_score:
            standing.losses += 1
        else:
            standing.ties += 1
    await db.commit()
    return game
