from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional

from app.db import get_db
from app.models import DraftPick, Player, Team
from app.schemas import DraftPickRead, PlayerRead
from app.services.draft import DraftSimulator, OffseasonManager, RookieGenerator

router = APIRouter(prefix="/draft", tags=["draft"])


@router.post("/conduct")
async def conduct_draft(
    year: int,
    auto_draft: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """Conduct the full draft for a given year."""
    
    simulator = DraftSimulator(db)
    
    try:
        drafted_players = await simulator.conduct_draft(year, auto_draft)
        
        return {
            "year": year,
            "auto_draft": auto_draft,
            "players_drafted": len(drafted_players),
            "drafted_players": [
                {
                    "id": player.id,
                    "name": player.name,
                    "position": player.pos,
                    "team_id": player.team_id,
                    "overall": player.ovr,
                    "potential": player.pot,
                }
                for player in drafted_players
            ]
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/picks")
async def get_draft_picks(
    year: int,
    team_id: Optional[int] = None,
    used: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get draft picks for a given year, optionally filtered by team or usage."""
    
    query = select(DraftPick).where(DraftPick.year == year)
    
    if team_id is not None:
        query = query.where(DraftPick.owned_by_team_id == team_id)
    
    if used is not None:
        query = query.where(DraftPick.used == used)
    
    query = query.order_by(DraftPick.overall)
    
    picks_result = await db.execute(query)
    picks = list(picks_result.scalars())
    
    return {
        "year": year,
        "team_id": team_id,
        "used": used,
        "total_picks": len(picks),
        "picks": [
            {
                "id": pick.id,
                "year": pick.year,
                "round": pick.round,
                "overall": pick.overall,
                "owned_by_team_id": pick.owned_by_team_id,
                "original_team_id": pick.original_team_id,
                "jj_value": pick.jj_value,
                "used": pick.used,
            }
            for pick in picks
        ]
    }


@router.post("/generate-picks")
async def generate_draft_picks(
    year: int,
    db: AsyncSession = Depends(get_db),
):
    """Generate draft picks for a given year."""
    
    offseason_manager = OffseasonManager(db)
    
    # Check if picks already exist for this year
    existing_picks_result = await db.execute(
        select(DraftPick).where(DraftPick.year == year)
    )
    existing_picks = list(existing_picks_result.scalars())
    
    if existing_picks:
        raise HTTPException(
            status_code=400, 
            detail=f"Draft picks already exist for year {year}"
        )
    
    # Generate picks
    draft_picks = await offseason_manager._generate_draft_picks(year)
    await db.commit()
    
    return {
        "year": year,
        "picks_generated": len(draft_picks),
        "rounds": 7,
    }


@router.post("/generate-rookies")
async def generate_rookie_class(
    year: int,
    size: int = 256,
    seed: Optional[int] = None,
):
    """Generate a preview of the rookie class for scouting."""
    
    generator = RookieGenerator(seed)
    rookie_class = generator.generate_rookie_class(year, size)
    
    return {
        "year": year,
        "class_size": len(rookie_class),
        "seed": seed,
        "rookies": [
            {
                "name": rookie.name,
                "position": rookie.position,
                "age": rookie.age,
                "height": rookie.height,
                "weight": rookie.weight,
                "college": rookie.college,
                "overall": rookie.ovr,
                "potential": rookie.pot,
                "speed": rookie.spd,
                "acceleration": rookie.acc,
                "agility": rookie.agi,
                "strength": rookie.str,
                "awareness": rookie.awr,
            }
            for rookie in rookie_class[:50]  # Return top 50 for preview
        ]
    }


@router.post("/trade-pick")
async def trade_draft_pick(
    pick_id: int,
    from_team_id: int,
    to_team_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Trade a draft pick between teams."""
    
    # Get the pick
    pick = await db.get(DraftPick, pick_id)
    if not pick:
        raise HTTPException(status_code=404, detail="Draft pick not found")
    
    # Verify the pick is owned by the from_team
    if pick.owned_by_team_id != from_team_id:
        raise HTTPException(
            status_code=400, 
            detail=f"Pick is not owned by team {from_team_id}"
        )
    
    # Verify both teams exist
    from_team = await db.get(Team, from_team_id)
    to_team = await db.get(Team, to_team_id)
    
    if not from_team or not to_team:
        raise HTTPException(status_code=404, detail="One or both teams not found")
    
    # Transfer ownership
    pick.owned_by_team_id = to_team_id
    
    await db.commit()
    await db.refresh(pick)
    
    return {
        "pick_id": pick.id,
        "year": pick.year,
        "round": pick.round,
        "overall": pick.overall,
        "from_team": from_team.name,
        "to_team": to_team.name,
        "jj_value": pick.jj_value,
    }


@router.post("/advance-offseason")
async def advance_offseason(
    completed_season: int,
    db: AsyncSession = Depends(get_db),
):
    """Process end-of-season activities and advance to offseason."""
    
    offseason_manager = OffseasonManager(db)
    results = await offseason_manager.advance_to_offseason(completed_season)
    
    return {
        "completed_season": completed_season,
        "next_season": completed_season + 1,
        **results
    }


@router.get("/board")
async def get_draft_board(
    year: int,
    position: Optional[str] = None,
    limit: int = 100,
):
    """Get a scouted draft board for evaluation."""
    
    generator = RookieGenerator()
    rookie_class = generator.generate_rookie_class(year, 300)
    
    # Filter by position if specified
    if position:
        rookie_class = [r for r in rookie_class if r.position == position]
    
    # Sort by overall + potential
    rookie_class.sort(key=lambda r: r.ovr + r.pot * 0.3, reverse=True)
    
    return {
        "year": year,
        "position_filter": position,
        "total_prospects": len(rookie_class),
        "showing": min(limit, len(rookie_class)),
        "prospects": [
            {
                "rank": idx + 1,
                "name": rookie.name,
                "position": rookie.position,
                "college": rookie.college,
                "age": rookie.age,
                "height": rookie.height,
                "weight": rookie.weight,
                "overall": rookie.ovr,
                "potential": rookie.pot,
                "grade": "A" if rookie.ovr >= 80 else "B" if rookie.ovr >= 70 else "C" if rookie.ovr >= 60 else "D",
                "projected_round": 1 if idx < 32 else 2 if idx < 64 else 3 if idx < 96 else 4 if idx < 128 else 5 if idx < 160 else 6 if idx < 192 else 7,
            }
            for idx, rookie in enumerate(rookie_class[:limit])
        ]
    }
