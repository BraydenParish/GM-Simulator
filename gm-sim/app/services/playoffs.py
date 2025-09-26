"""Playoff bracket generation and simulation utilities."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

from app.services.injuries import InjuryEngine, PlayerParticipation
from app.services.llm import OpenRouterClient
from app.services.sim import simulate_game
from app.services.analytics import compute_drive_analytics


@dataclass(slots=True)
class PlayoffSeed:
    """Metadata about a seeded playoff team."""

    seed: int
    team_id: int
    name: str
    abbr: str
    rating: float
    wins: int
    losses: int
    ties: int
    points_for: int
    points_against: int


@dataclass(slots=True)
class PlayoffGameLog:
    """Result of a single playoff matchup."""

    round_number: int
    round_name: str
    matchup: int
    home_seed: PlayoffSeed
    away_seed: PlayoffSeed
    home_score: int
    away_score: int
    headline: str
    drives: List[Dict[str, int | str | float]]
    player_stats: Dict[str, Sequence[Dict[str, int | str]]]
    box_score: Dict[str, object]
    winner_seed: PlayoffSeed
    recap: Optional[str] = None
    narrative_facts: Optional[Dict[str, object]] = None
    analytics: Optional[Dict[str, Any]] = None


class PlayoffSimulator:
    """Single-elimination playoff simulator built on the core game engine."""

    def __init__(
        self,
        seeds: Iterable[PlayoffSeed],
        *,
        narrative_client: Optional[OpenRouterClient] = None,
        injury_engine: Optional[InjuryEngine] = None,
        rosters: Optional[Dict[int, List[PlayerParticipation]]] = None,
        rng_seed: Optional[int] = None,
    ) -> None:
        ordered = sorted(seeds, key=lambda seed: seed.seed)
        if len(ordered) < 2:
            raise ValueError("At least two seeds required for playoff simulation")
        if not self._is_power_of_two(len(ordered)):
            raise ValueError("Playoff bracket size must be a power of two")
        self._seeds = ordered
        self._narrative_client = narrative_client
        self._injury_engine = injury_engine
        self._rng = random.Random(rng_seed)
        self._games: List[PlayoffGameLog] = []
        if injury_engine is not None:
            if rosters is None:
                self._rosters = {seed.team_id: [] for seed in ordered}
            else:
                self._rosters = {
                    seed.team_id: list(rosters.get(seed.team_id, [])) for seed in ordered
                }
        else:
            self._rosters = {seed.team_id: [] for seed in ordered}

    @staticmethod
    def _is_power_of_two(value: int) -> bool:
        return value > 0 and value & (value - 1) == 0

    @staticmethod
    def _round_name(teams_remaining: int) -> str:
        lookup = {
            2: "Championship",
            4: "Semifinals",
            8: "Quarterfinals",
            16: "Round of 16",
        }
        return lookup.get(teams_remaining, f"Round of {teams_remaining}")

    async def simulate(self) -> List[PlayoffGameLog]:
        """Run the playoff bracket to completion."""

        current_seeds = list(self._seeds)
        round_number = 1
        while len(current_seeds) > 1:
            round_name = self._round_name(len(current_seeds))
            matchups = self._pair_matchups(current_seeds)
            games_in_round = len(matchups)
            winners: List[PlayoffSeed] = []
            for matchup_index, (higher_seed, lower_seed) in enumerate(matchups, start=1):
                game_log = await self._play_game(
                    round_number,
                    round_name,
                    matchup_index,
                    higher_seed,
                    lower_seed,
                    games_in_round,
                )
                winners.append(game_log.winner_seed)
                self._games.append(game_log)
            if self._injury_engine is not None:
                self._injury_engine.rest_week(self._rosters)
            current_seeds = sorted(winners, key=lambda seed: seed.seed)
            round_number += 1
        return list(self._games)

    def games(self) -> List[PlayoffGameLog]:
        return list(self._games)

    def champion(self) -> PlayoffSeed:
        if not self._games:
            raise ValueError("No games have been simulated")
        final_game = max(self._games, key=lambda game: game.round_number)
        return final_game.winner_seed

    def _pair_matchups(
        self, seeds: Sequence[PlayoffSeed]
    ) -> List[tuple[PlayoffSeed, PlayoffSeed]]:
        pairings: List[tuple[PlayoffSeed, PlayoffSeed]] = []
        total = len(seeds)
        for index in range(total // 2):
            pairings.append((seeds[index], seeds[total - index - 1]))
        return pairings

    async def _play_game(
        self,
        round_number: int,
        round_name: str,
        matchup_index: int,
        higher_seed: PlayoffSeed,
        lower_seed: PlayoffSeed,
        games_in_round: int,
    ) -> PlayoffGameLog:
        home_roster = self._rosters.get(higher_seed.team_id)
        away_roster = self._rosters.get(lower_seed.team_id)
        home_rating = higher_seed.rating
        away_rating = lower_seed.rating
        if self._injury_engine is not None:
            home_penalty = self._injury_engine.team_availability_penalty(home_roster or [])
            away_penalty = self._injury_engine.team_availability_penalty(away_roster or [])
            home_rating = max(1.0, home_rating - home_penalty)
            away_rating = max(1.0, away_rating - away_penalty)
        sim_seed = self._rng.randint(0, 1_000_000)
        result = simulate_game(
            higher_seed.team_id,
            lower_seed.team_id,
            home_rating,
            away_rating,
            home_roster=home_roster,
            away_roster=away_roster,
            seed=sim_seed,
        )
        home_score = int(result["home_score"])
        away_score = int(result["away_score"])
        winner = higher_seed if home_score >= away_score else lower_seed

        recap_summary: Optional[str] = None
        recap_facts: Optional[Dict[str, object]] = None
        if self._narrative_client is not None:
            remaining_games = max(0, self._expected_total_games() - len(self._games) - 1)
            context = {
                "teams": {"home": higher_seed.name, "away": lower_seed.name},
                "score": {"home": home_score, "away": away_score},
                "headline": result.get("headline", ""),
                "key_players": result.get("player_stats", {}).get("home", [])
                + result.get("player_stats", {}).get("away", []),
                "progress_summary": (
                    f"Completed round {round_number} game {matchup_index} of {games_in_round}"
                ),
                "remaining_tasks": f"{remaining_games} playoff games remaining",
            }
            narrative = await self._narrative_client.generate_game_recap(context)
            recap_summary = narrative.summary
            recap_facts = narrative.facts

        return PlayoffGameLog(
            round_number=round_number,
            round_name=round_name,
            matchup=matchup_index,
            home_seed=higher_seed,
            away_seed=lower_seed,
            home_score=home_score,
            away_score=away_score,
            headline=str(result.get("headline", "")),
            drives=list(result.get("drives", [])),
            player_stats={
                "home": list(result.get("player_stats", {}).get("home", [])),
                "away": list(result.get("player_stats", {}).get("away", [])),
            },
            box_score=dict(result.get("box", {})),
            winner_seed=winner,
            recap=recap_summary,
            narrative_facts=recap_facts,
            analytics=compute_drive_analytics(
                drives=result.get("drives", []),
                home_score=home_score,
                away_score=away_score,
            ),
        )

    def _expected_total_games(self) -> int:
        return len(self._seeds) - 1
