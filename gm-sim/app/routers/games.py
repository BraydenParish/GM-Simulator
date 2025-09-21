from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import (
    Game,
    Player,
    PlayerGameStat,
    PlayerSeasonStat,
    TeamSeasonStat,
    Standing,
    Team,
)
from app.schemas import GameRead
from app.services.sim import simulate_game

router = APIRouter(prefix="/games", tags=["games"])


@router.post("/simulate", response_model=GameRead)
async def simulate_game_endpoint(
    home_team_id: int,
    away_team_id: int,
    season: int,
    week: int,
    sim_seed: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    # Get teams
    home_team = (
        await db.execute(select(Team).where(Team.id == home_team_id))
    ).scalar_one_or_none()
    away_team = (
        await db.execute(select(Team).where(Team.id == away_team_id))
    ).scalar_one_or_none()
    if not home_team or not away_team:
        raise HTTPException(status_code=404, detail="Team not found")
    home_rating = home_team.elo
    away_rating = away_team.elo

    home_roster: List[Player] = (
        (await db.execute(select(Player).where(Player.team_id == home_team_id)))
        .scalars()
        .all()
    )
    away_roster: List[Player] = (
        (await db.execute(select(Player).where(Player.team_id == away_team_id)))
        .scalars()
        .all()
    )

    sim_result = simulate_game(
        home_team_id,
        away_team_id,
        home_rating,
        away_rating,
        seed=sim_seed,
        home_roster=home_roster,
        away_roster=away_roster,
    )
    game = Game(
        season=season,
        week=week,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_score=sim_result["home_score"],
        away_score=sim_result["away_score"],
        sim_seed=sim_seed,
        box_json=sim_result["box"],
        injuries_json=None,
    )
    db.add(game)
    await db.flush()

    team_totals: Dict[int, Dict[str, int]] = {}

    for stat in sim_result.get("player_stats", []):
        player_id = stat["player_id"]
        team_id = stat["team_id"]
        stats_payload: Dict[str, int] = stat["stats"]

        game_stat = PlayerGameStat(
            game_id=game.id,
            player_id=player_id,
            team_id=team_id,
            season=season,
            week=week,
            stats=stats_payload,
        )
        db.add(game_stat)

        season_stat = (
            await db.execute(
                select(PlayerSeasonStat).where(
                    PlayerSeasonStat.season == season,
                    PlayerSeasonStat.player_id == player_id,
                )
            )
        ).scalar_one_or_none()
        if not season_stat:
            season_stat = PlayerSeasonStat(
                season=season,
                player_id=player_id,
                team_id=team_id,
                games_played=0,
                stats={key: 0 for key in stats_payload},
            )
            db.add(season_stat)
        else:
            season_stat.team_id = team_id
        season_stat.games_played += 1
        merged_stats = dict(season_stat.stats)
        for key, value in stats_payload.items():
            merged_stats[key] = merged_stats.get(key, 0) + value
        season_stat.stats = merged_stats

        team_line = team_totals.setdefault(team_id, {})
        for key, value in stats_payload.items():
            team_line[key] = team_line.get(key, 0) + value

    for team_id, totals in team_totals.items():
        team_season_stat = (
            await db.execute(
                select(TeamSeasonStat).where(
                    TeamSeasonStat.season == season,
                    TeamSeasonStat.team_id == team_id,
                )
            )
        ).scalar_one_or_none()

        if not team_season_stat:
            team_season_stat = TeamSeasonStat(
                season=season,
                team_id=team_id,
                games_played=0,
                stats={key: 0 for key in totals},
            )
            db.add(team_season_stat)

        team_season_stat.games_played += 1
        merged_team_stats = dict(team_season_stat.stats or {})
        for key, value in totals.items():
            merged_team_stats[key] = merged_team_stats.get(key, 0) + value
        team_season_stat.stats = merged_team_stats

    await db.commit()
    await db.refresh(game)
    # Update standings (minimal)
    for team, score, opp_score in [
        (home_team, sim_result["home_score"], sim_result["away_score"]),
        (away_team, sim_result["away_score"], sim_result["home_score"]),
    ]:
        standing = (
            await db.execute(
                select(Standing).where(
                    Standing.season == season, Standing.team_id == team.id
                )
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
