from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional

from app.db import get_db
from app.models import Player, PlayerStamina, Injury
from app.services.development import PlayerDevelopmentEngine, StaminaManager, TrainingCampManager
from app.services.injuries import InjuryEngine

router = APIRouter(prefix="/development", tags=["development"])


@router.post("/process-offseason")
async def process_offseason_development(
    seed: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Process player development for the entire league during offseason."""
    
    engine = PlayerDevelopmentEngine(seed)
    events = await engine.process_offseason_development(db)
    
    # Group events by type
    development_events = [e for e in events if e.reason == "development"]
    aging_events = [e for e in events if e.reason == "aging"]
    
    return {
        "total_events": len(events),
        "development_events": len(development_events),
        "aging_events": len(aging_events),
        "events": [
            {
                "player_id": event.player_id,
                "attribute": event.attribute,
                "old_value": event.old_value,
                "new_value": event.new_value,
                "change": event.new_value - event.old_value,
                "reason": event.reason,
            }
            for event in events[:100]  # Limit to first 100 for response size
        ]
    }


@router.post("/training-camp")
async def run_training_camp(
    team_id: int,
    focus_areas: Optional[List[str]] = None,
    db: AsyncSession = Depends(get_db),
):
    """Run training camp for a team with optional position focus."""
    
    development_engine = PlayerDevelopmentEngine()
    camp_manager = TrainingCampManager(development_engine)
    
    events = await camp_manager.run_training_camp(db, team_id, focus_areas)
    
    return {
        "team_id": team_id,
        "focus_areas": focus_areas or [],
        "improvements": len(events),
        "events": [
            {
                "player_id": event.player_id,
                "attribute": event.attribute,
                "old_value": event.old_value,
                "new_value": event.new_value,
                "change": event.new_value - event.old_value,
                "reason": event.reason,
            }
            for event in events
        ]
    }


@router.get("/player-development/{player_id}")
async def get_player_development_profile(
    player_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get development profile and projections for a player."""
    
    player = await db.get(Player, player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    # Get stamina info
    stamina_manager = StaminaManager()
    fatigue = await stamina_manager.get_player_fatigue(db, player_id)
    
    # Calculate development potential
    development_engine = PlayerDevelopmentEngine()
    position_group = development_engine._get_position_group(player.pos or "")
    prime_start, prime_end = development_engine.PRIME_AGES.get(position_group, (25, 30))
    
    age = player.age or 25
    development_rate = development_engine.DEVELOPMENT_RATES.get(age, 0.0)
    
    # Injury history
    injuries_result = await db.execute(
        select(Injury).where(Injury.player_id == player_id).order_by(Injury.occurred_at.desc()).limit(5)
    )
    recent_injuries = list(injuries_result.scalars())
    
    return {
        "player_id": player_id,
        "name": player.name,
        "position": player.pos,
        "age": age,
        "current_overall": player.ovr,
        "potential": player.pot,
        "development_profile": {
            "position_group": position_group,
            "prime_age_range": f"{prime_start}-{prime_end}",
            "current_development_rate": development_rate,
            "years_to_prime": max(0, prime_start - age),
            "years_past_prime": max(0, age - prime_end),
            "potential_remaining": max(0, (player.pot or 0) - (player.ovr or 0)),
        },
        "physical_condition": {
            "fatigue_level": fatigue,
            "injury_status": player.injury_status,
            "stamina": player.stamina,
        },
        "recent_injuries": [
            {
                "type": injury.type,
                "severity": injury.severity,
                "weeks_out": injury.expected_weeks_out,
                "occurred_at": injury.occurred_at.isoformat() if injury.occurred_at else None,
            }
            for injury in recent_injuries
        ]
    }


@router.post("/weekly-recovery")
async def process_weekly_recovery(
    db: AsyncSession = Depends(get_db),
):
    """Process weekly stamina recovery and injury healing."""
    
    stamina_manager = StaminaManager()
    await stamina_manager.weekly_stamina_recovery(db)
    
    # Count stamina records processed
    stamina_result = await db.execute(select(PlayerStamina))
    stamina_count = len(list(stamina_result.scalars()))
    
    # Process injury recovery (reduce weeks remaining)
    injuries_result = await db.execute(
        select(Injury).where(Injury.expected_weeks_out > 0)
    )
    active_injuries = list(injuries_result.scalars())
    
    recovered_players = []
    for injury in active_injuries:
        injury.expected_weeks_out = max(0, injury.expected_weeks_out - 1)
        
        if injury.expected_weeks_out == 0:
            # Player recovered
            player = await db.get(Player, injury.player_id)
            if player:
                player.injury_status = "OK"
                recovered_players.append(player.id)
    
    await db.commit()
    
    return {
        "stamina_recoveries": stamina_count,
        "injuries_processed": len(active_injuries),
        "players_recovered": len(recovered_players),
        "recovered_player_ids": recovered_players,
    }


@router.get("/injury-report")
async def get_injury_report(
    team_id: Optional[int] = None,
    active_only: bool = True,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """Get current injury report, optionally filtered by team."""
    
    query = select(Injury).join(Player)
    
    if team_id is not None:
        query = query.where(Player.team_id == team_id)
    
    if active_only:
        query = query.where(Injury.expected_weeks_out > 0)
    
    query = query.order_by(Injury.occurred_at.desc()).limit(limit)
    
    injuries_result = await db.execute(query)
    injuries = list(injuries_result.scalars())
    
    # Get player names
    injury_data = []
    for injury in injuries:
        player = await db.get(Player, injury.player_id)
        if player:
            injury_data.append({
                "injury_id": injury.id,
                "player_id": injury.player_id,
                "player_name": player.name,
                "position": player.pos,
                "team_id": injury.team_id,
                "injury_type": injury.type,
                "severity": injury.severity,
                "weeks_remaining": injury.expected_weeks_out,
                "occurred_at": injury.occurred_at.isoformat() if injury.occurred_at else None,
            })
    
    return {
        "team_id": team_id,
        "active_only": active_only,
        "total_injuries": len(injury_data),
        "injuries": injury_data,
    }


@router.post("/simulate-injuries")
async def simulate_game_injuries(
    team_id: int,
    snaps_played: int = 60,
    game_intensity: float = 1.0,
    db: AsyncSession = Depends(get_db),
):
    """Simulate injuries for a team during a game (for testing)."""
    
    # Get team players
    players_result = await db.execute(
        select(Player).where(Player.team_id == team_id)
    )
    players = list(players_result.scalars())
    
    if not players:
        raise HTTPException(status_code=404, detail="No players found for team")
    
    # Create injury engine and simulate
    injury_engine = InjuryEngine()
    
    # Create participant data
    from app.services.injuries import PlayerParticipation
    participants = [
        PlayerParticipation(
            player_id=player.id,
            position=player.pos or "UNKNOWN",
            snaps=snaps_played,
            player_name=player.name,
        )
        for player in players[:22]  # Simulate for starters only
    ]
    
    # Simulate injuries
    injury_events = injury_engine.simulate_game(team_id, participants)
    
    # Save injuries to database
    for event in injury_events:
        injury = Injury(
            player_id=event.player_id,
            team_id=event.team_id,
            game_id=0,  # No specific game for testing
            type=event.injury_type,
            severity=event.severity,
            expected_weeks_out=event.weeks_out,
        )
        db.add(injury)
        
        # Update player status
        player = await db.get(Player, event.player_id)
        if player:
            player.injury_status = f"{event.severity.title()} {event.injury_type}"
    
    await db.commit()
    
    return {
        "team_id": team_id,
        "snaps_simulated": snaps_played,
        "game_intensity": game_intensity,
        "injuries_occurred": len(injury_events),
        "injuries": [
            {
                "player_id": event.player_id,
                "injury_type": event.injury_type,
                "severity": event.severity,
                "weeks_out": event.weeks_out,
                "occurred_snap": event.occurred_snap,
            }
            for event in injury_events
        ]
    }


@router.get("/fatigue-report")
async def get_fatigue_report(
    team_id: Optional[int] = None,
    threshold: float = 50.0,
    db: AsyncSession = Depends(get_db),
):
    """Get players with high fatigue levels."""
    
    query = select(PlayerStamina).join(Player)
    
    if team_id is not None:
        query = query.where(Player.team_id == team_id)
    
    query = query.where(PlayerStamina.fatigue >= threshold)
    query = query.order_by(PlayerStamina.fatigue.desc())
    
    stamina_result = await db.execute(query)
    stamina_records = list(stamina_result.scalars())
    
    fatigue_data = []
    for record in stamina_records:
        player = await db.get(Player, record.player_id)
        if player:
            fatigue_data.append({
                "player_id": record.player_id,
                "player_name": player.name,
                "position": player.pos,
                "team_id": player.team_id,
                "fatigue_level": record.fatigue,
                "last_updated": record.updated_at.isoformat() if record.updated_at else None,
            })
    
    return {
        "team_id": team_id,
        "fatigue_threshold": threshold,
        "high_fatigue_players": len(fatigue_data),
        "players": fatigue_data,
    }
