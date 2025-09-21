from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db import get_db
from app.models import Game, Standing, Team
from app.schemas import GameRead
from app.services.sim import simulate_game
from app.services.ratings import compute_team_rating
from app.services.llm import OpenRouterClient
from app.services.state import GameStateStore
from typing import Dict
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/games", tags=["games"])


@router.post("/simulate", response_model=GameRead)
async def simulate_game_endpoint(
    home_team_id: int,
    away_team_id: int,
    season: int,
    week: int,
    generate_narrative: bool = True,
    db: AsyncSession = Depends(get_db),
):
    # Get teams
    home_team = (await db.execute(select(Team).where(Team.id == home_team_id))).scalar_one_or_none()
    away_team = (await db.execute(select(Team).where(Team.id == away_team_id))).scalar_one_or_none()
    if not home_team or not away_team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    # Get roster participation data
    state_store = GameStateStore(db)
    participant_rosters = await state_store.participant_rosters()
    home_roster = participant_rosters.get(home_team_id, [])
    away_roster = participant_rosters.get(away_team_id, [])
    
    # For MVP, use team elo as rating
    home_rating = home_team.elo
    away_rating = away_team.elo
    sim_result = simulate_game(
        home_team_id, 
        away_team_id, 
        home_rating, 
        away_rating,
        home_roster=home_roster,
        away_roster=away_roster
    )
    
    # Generate narrative if requested
    narrative_recap = None
    narrative_facts = None
    if generate_narrative:
        try:
            llm_client = OpenRouterClient()
            state_snapshot = await state_store.snapshot_for_game([home_team_id, away_team_id])
            
            game_context = {
                "teams": {"home": home_team.name, "away": away_team.name},
                "score": {"home": sim_result["home_score"], "away": sim_result["away_score"]},
                "headline": sim_result["headline"],
                "key_players": sim_result["player_stats"]["home"] + sim_result["player_stats"]["away"],
                "state": state_snapshot,
                "progress_summary": f"Simulated {away_team.name} @ {home_team.name} Week {week}",
                "remaining_tasks": f"Continue season simulation for Week {week + 1}",
            }
            
            recap = await llm_client.generate_game_recap(game_context)
            narrative_recap = recap.summary
            narrative_facts = recap.facts
            logger.info(f"Generated narrative for game {home_team.name} vs {away_team.name}")
        except Exception as e:
            logger.warning(f"Failed to generate narrative for game: {e}")
            # Continue without narrative - don't fail the entire simulation
    
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
        narrative_recap=narrative_recap,
        narrative_facts=narrative_facts,
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
