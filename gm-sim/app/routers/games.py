from __future__ import annotations

from typing import Dict, Iterable, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Game, Injury, Player, PlayerStamina, Standing, Team
from app.schemas import GameRead
from app.services.injuries import InjuryEngine, PlayerParticipation
from app.services.sim import simulate_game
from app.services.state import GameStateStore


def _participants_for_team(
    roster_map: Dict[int, List[PlayerParticipation]], team_id: int
) -> List[PlayerParticipation]:
    participants = roster_map.get(team_id, [])
    # ensure we always return a mutable copy the injury engine can mutate safely
    return [PlayerParticipation(**participant.__dict__) for participant in participants]


async def _persist_fatigue(
    session: AsyncSession,
    participants: Iterable[PlayerParticipation],
) -> None:
    if not participants:
        return
    player_ids = {p.player_id for p in participants}
    if not player_ids:
        return
    existing_rows = (
        await session.execute(select(PlayerStamina).where(PlayerStamina.player_id.in_(player_ids)))
    ).scalars()
    stamina_by_player = {row.player_id: row for row in existing_rows}
    for participant in participants:
        stamina_row = stamina_by_player.get(participant.player_id)
        if stamina_row is None:
            stamina_row = PlayerStamina(
                player_id=participant.player_id, fatigue=float(participant.fatigue)
            )
            session.add(stamina_row)
        else:
            stamina_row.fatigue = float(participant.fatigue)


async def _update_player_status(
    session: AsyncSession,
    injuries: Iterable[Injury],
) -> None:
    if not injuries:
        return
    player_ids = {injury.player_id for injury in injuries}
    if not player_ids:
        return
    players = (await session.execute(select(Player).where(Player.id.in_(player_ids)))).scalars()
    status_by_player = {injury.player_id: injury for injury in injuries}
    for player in players:
        injury = status_by_player.get(player.id)
        if injury is None:
            continue
        weeks = max(injury.expected_weeks_out, 0)
        descriptor = f"{injury.severity.title()} ({weeks}w)"
        if injury.type:
            descriptor = f"{descriptor} - {injury.type}"
        player.injury_status = descriptor


async def _game_injury_payload(
    session: AsyncSession,
    game: Game,
    injuries: List[Injury],
) -> None:
    if not injuries:
        game.injuries_json = []
        return
    await _update_player_status(session, injuries)
    game.injuries_json = [
        {
            "player_id": injury.player_id,
            "team_id": injury.team_id,
            "severity": injury.severity,
            "weeks_out": injury.expected_weeks_out,
            "injury_type": injury.type,
            "occurred_snap": injury.occurred_at_play_id,
        }
        for injury in injuries
    ]


router = APIRouter(prefix="/games", tags=["games"])


@router.post("/simulate", response_model=GameRead)
async def simulate_game_endpoint(
    home_team_id: int,
    away_team_id: int,
    season: int,
    week: int,
    db: AsyncSession = Depends(get_db),
):
    home_team = (await db.execute(select(Team).where(Team.id == home_team_id))).scalar_one_or_none()
    away_team = (await db.execute(select(Team).where(Team.id == away_team_id))).scalar_one_or_none()
    if not home_team or not away_team:
        raise HTTPException(status_code=404, detail="Team not found")

    home_rating = home_team.elo
    away_rating = away_team.elo
    sim_result = simulate_game(home_team_id, away_team_id, home_rating, away_rating)

    state_store = GameStateStore(db)
    roster_map = await state_store.participant_rosters()
    injury_engine = InjuryEngine()

    home_participants = _participants_for_team(roster_map, home_team_id)
    away_participants = _participants_for_team(roster_map, away_team_id)

    injuries_raw = []
    if home_participants:
        injuries_raw.extend(injury_engine.simulate_game(home_team_id, home_participants))
    if away_participants:
        injuries_raw.extend(injury_engine.simulate_game(away_team_id, away_participants))

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
    await db.flush()

    injuries: List[Injury] = []
    for event in injuries_raw:
        injuries.append(
            Injury(
                player_id=event.player_id,
                team_id=event.team_id,
                game_id=game.id,
                type=event.injury_type,
                severity=event.severity,
                expected_weeks_out=event.weeks_out,
                occurred_at_play_id=event.occurred_snap,
            )
        )
    db.add_all(injuries)

    await _game_injury_payload(db, game, injuries)
    await _persist_fatigue(db, home_participants + away_participants)

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
    await db.refresh(game)
    return game
