from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import PlayoffGame, Standing, Team
from app.schemas import ChampionSummary, PlayoffGameRead, PlayoffSimulationResponse
from app.services.coaching import CoachingSystem
from app.services.llm import OpenRouterClient
from app.services.playoffs import PlayoffSeed, PlayoffSimulator

router = APIRouter(prefix="/playoffs", tags=["playoffs"])


def _validate_bracket_size(value: int) -> None:
    if value < 2:
        raise HTTPException(status_code=400, detail="bracket_size must be at least 2")
    if value & (value - 1) != 0:
        raise HTTPException(status_code=400, detail="bracket_size must be a power of two")


@router.post("/simulate", response_model=PlayoffSimulationResponse)
async def simulate_playoffs(
    season: int,
    bracket_size: int = 8,
    generate_narratives: bool = False,
    use_injuries: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Seed the playoff bracket from standings and simulate the postseason."""

    _validate_bracket_size(bracket_size)

    standings_result = await db.execute(
        select(Standing).where(Standing.season == season)
    )
    standings = list(standings_result.scalars())
    if not standings:
        raise HTTPException(
            status_code=404, detail=f"No standings recorded for season {season}"
        )

    teams_result = await db.execute(select(Team))
    teams = {team.id: team for team in teams_result.scalars()}

    sorted_standings = sorted(
        standings,
        key=lambda record: (
            -record.wins,
            record.losses,
            -record.ties,
            -record.pf,
            record.pa,
            -(teams.get(record.team_id).elo if teams.get(record.team_id) else 0),
        ),
    )

    if len(sorted_standings) < bracket_size:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Not enough teams with standings for bracket size {bracket_size}; "
                f"found {len(sorted_standings)}"
            ),
        )

    seeds = []
    for index, standing in enumerate(sorted_standings[:bracket_size], start=1):
        team = teams.get(standing.team_id)
        if team is None:
            raise HTTPException(
                status_code=400,
                detail=f"Team {standing.team_id} missing from teams table",
            )
        seeds.append(
            PlayoffSeed(
                seed=index,
                team_id=team.id,
                name=team.name,
                abbr=team.abbr,
                rating=team.elo or 1500,
                wins=standing.wins,
                losses=standing.losses,
                ties=standing.ties,
                points_for=standing.pf,
                points_against=standing.pa,
            )
        )

    narrative_client = None
    if generate_narratives:
        narrative_client = OpenRouterClient()
        if not narrative_client.api_key:
            raise HTTPException(
                status_code=400,
                detail="OpenRouter API key not configured. Set OPENROUTER_API_KEY.",
            )

    injury_engine = None
    if use_injuries:
        from app.services.injuries import InjuryEngine

        injury_engine = InjuryEngine()

    coaching_system = await CoachingSystem.build(db)

    simulator = PlayoffSimulator(
        seeds,
        narrative_client=narrative_client,
        injury_engine=injury_engine,
        rng_seed=season,
        coaching_system=coaching_system,
    )

    games = await simulator.simulate()
    champion = simulator.champion()

    await db.execute(delete(PlayoffGame).where(PlayoffGame.season == season))

    response_games: list[PlayoffGameRead] = []
    for game in games:
        db_game = PlayoffGame(
            season=season,
            round_name=game.round_name,
            round_number=game.round_number,
            matchup=game.matchup,
            home_team_id=game.home_seed.team_id,
            away_team_id=game.away_seed.team_id,
            home_seed=game.home_seed.seed,
            away_seed=game.away_seed.seed,
            home_score=game.home_score,
            away_score=game.away_score,
            winner_team_id=game.winner_seed.team_id,
            headline=game.headline,
            box_json={
                "drives": game.drives,
                "player_stats": game.player_stats,
                "box": game.box_score,
                "analytics": game.analytics,
            },
            narrative_recap=game.recap,
            narrative_facts=game.narrative_facts,
        )
        db.add(db_game)

        response_games.append(
            PlayoffGameRead(
                round_number=game.round_number,
                round_name=game.round_name,
                matchup=game.matchup,
                home_team_id=game.home_seed.team_id,
                home_seed=game.home_seed.seed,
                home_team=game.home_seed.name,
                away_team_id=game.away_seed.team_id,
                away_seed=game.away_seed.seed,
                away_team=game.away_seed.name,
                home_score=game.home_score,
                away_score=game.away_score,
                winner_team_id=game.winner_seed.team_id,
                winner_seed=game.winner_seed.seed,
                headline=game.headline,
                narrative_recap=game.recap,
            )
        )

    await db.commit()

    return PlayoffSimulationResponse(
        season=season,
        bracket_size=len(seeds),
        generated_narratives=bool(narrative_client),
        games=response_games,
        champion=ChampionSummary(
            team_id=champion.team_id,
            seed=champion.seed,
            name=champion.name,
            abbr=champion.abbr,
        ),
    )
