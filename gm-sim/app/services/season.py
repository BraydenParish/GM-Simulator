"""Season orchestration utilities for the GM simulator."""

from __future__ import annotations

import asyncio
import random
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from app.services.llm import OpenRouterClient
from app.services.sim import simulate_game
from app.services.injuries import InjuryEngine, InjuryEvent, PlayerParticipation
from app.services.state import GameStateStore, attach_names_to_participants


@dataclass
class TeamSeed:
    id: int
    name: str
    abbr: str
    rating: float


@dataclass
class TeamStanding:
    wins: int = 0
    losses: int = 0
    ties: int = 0
    points_for: int = 0
    points_against: int = 0

    def record_result(self, scored: int, allowed: int) -> None:
        self.points_for += scored
        self.points_against += allowed
        if scored > allowed:
            self.wins += 1
        elif scored < allowed:
            self.losses += 1
        else:
            self.ties += 1


@dataclass
class PlayerStatLine:
    player: str
    summary: str
    week: int


@dataclass
class GameLog:
    week: int
    home_team_id: int
    away_team_id: int
    home_score: int
    away_score: int
    win_prob: float
    drives: List[Dict[str, int | str | float]]
    headline: str
    recap: Optional[str] = None
    injuries: List[InjuryEvent] = field(default_factory=list)
    narrative_facts: Optional[Dict[str, object]] = None


class SeasonSimulator:
    """Lightweight round-robin season simulator with narrative hooks."""

    def __init__(
        self,
        teams: Iterable[TeamSeed],
        *,
        narrative_client: Optional[OpenRouterClient] = None,
        rng_seed: Optional[int] = None,
        injury_engine: Optional[InjuryEngine] = None,
        rosters: Optional[Dict[int, List[PlayerParticipation]]] = None,
        state_store: Optional[GameStateStore] = None,
        season_year: int = 2024,
    ) -> None:
        self.teams: List[TeamSeed] = list(teams)
        if not self.teams:
            raise ValueError("SeasonSimulator requires at least one team")
        self.narrative_client = narrative_client
        self._random = random.Random(rng_seed)
        self._standings: Dict[int, TeamStanding] = {team.id: TeamStanding() for team in self.teams}
        self._player_stats: Dict[int, List[PlayerStatLine]] = {team.id: [] for team in self.teams}
        self._games: List[GameLog] = []
        self._injury_history: List[InjuryEvent] = []
        self.schedule = self._build_schedule()
        self._total_games = sum(len(week) for week in self.schedule)
        self.injury_engine = injury_engine
        self.state_store = state_store
        self.season_year = season_year
        if self.injury_engine and rosters is None:
            raise ValueError("Rosters must be provided when using an injury engine")
        if rosters is None:
            self._rosters: Dict[int, List[PlayerParticipation]] = {
                team.id: [] for team in self.teams
            }
        else:
            self._rosters = {team.id: deepcopy(rosters.get(team.id, [])) for team in self.teams}

    def _build_schedule(self) -> List[List[Tuple[int, int]]]:
        ids = [team.id for team in self.teams]
        if len(ids) == 1:
            return [[]]
        if len(ids) % 2 == 1:
            ids.append(None)  # type: ignore[arg-type]
        weeks = len(ids) - 1
        schedule: List[List[Tuple[int, int]]] = []
        for week in range(weeks):
            pairings: List[Tuple[int, int]] = []
            for i in range(len(ids) // 2):
                home = ids[i]
                away = ids[-1 - i]
                if home is None or away is None:
                    continue
                if week % 2 == 0:
                    pairings.append((home, away))
                else:
                    pairings.append((away, home))
            schedule.append(pairings)
            ids = [ids[0]] + ids[-1:] + ids[1:-1]
        return schedule

    async def simulate_week(self, week_index: int, matchups: List[Tuple[int, int]]) -> None:
        total_weeks = len(self.schedule)
        games_in_week = len(matchups)
        for matchup_index, (home_id, away_id) in enumerate(matchups, start=1):
            home_team = self._get_team(home_id)
            away_team = self._get_team(away_id)
            home_rating = home_team.rating
            away_rating = away_team.rating
            injuries: List[InjuryEvent] = []
            if self.injury_engine is not None:
                home_roster = self._rosters.get(home_id, [])
                away_roster = self._rosters.get(away_id, [])
                home_penalty = self.injury_engine.team_availability_penalty(home_roster)
                away_penalty = self.injury_engine.team_availability_penalty(away_roster)
                home_rating = max(1.0, home_rating - home_penalty)
                away_rating = max(1.0, away_rating - away_penalty)
            seed = self._random.randint(0, 1_000_000)
            result = simulate_game(
                home_id,
                away_id,
                home_rating,
                away_rating,
                home_roster=self._rosters.get(home_id),
                away_roster=self._rosters.get(away_id),
                seed=seed,
            )
            recap_summary: Optional[str] = None
            recap_facts: Optional[Dict[str, object]] = None
            if self.narrative_client is not None:
                games_completed = len(self._games)
                remaining_games = max(self._total_games - games_completed - 1, 0)
                progress_summary = (
                    f"Finished {max(week_index - 1, 0)} of {total_weeks} weeks; "
                    f"currently simulating week {week_index} matchup {matchup_index} of {max(games_in_week, 1)}."
                )
                remaining_tasks = (
                    f"{max(total_weeks - week_index, 0)} weeks remain after this game; "
                    f"{remaining_games} games left overall."
                )
                state_snapshot: Optional[Dict[str, object]] = None
                if self.state_store is not None:
                    state_snapshot = await self.state_store.snapshot_for_game([home_id, away_id])
                context = {
                    "teams": {"home": home_team.name, "away": away_team.name},
                    "score": {"home": result["home_score"], "away": result["away_score"]},
                    "headline": result.get("headline", ""),
                    "key_players": result.get("player_stats", {}).get("home", [])
                    + result.get("player_stats", {}).get("away", []),
                    "progress_summary": progress_summary,
                    "remaining_tasks": remaining_tasks,
                    "state": state_snapshot,
                }
                narrative = await self.narrative_client.generate_game_recap(context)
                recap_summary = narrative.summary
                recap_facts = narrative.facts
            if self.injury_engine is not None:
                home_roster = self._rosters.get(home_id, [])
                away_roster = self._rosters.get(away_id, [])
                injuries.extend(self.injury_engine.simulate_game(home_id, home_roster))
                injuries.extend(self.injury_engine.simulate_game(away_id, away_roster))
            self._record_game(
                week_index,
                home_team,
                away_team,
                result,
                recap=recap_summary,
                narrative_facts=recap_facts,
                injuries=injuries,
            )
        if self.injury_engine is not None and matchups:
            self.injury_engine.rest_week(self._rosters)

    async def simulate_season(self) -> List[GameLog]:
        if self.state_store is not None:
            snapshot = await self.state_store.snapshot()
            attach_names_to_participants(snapshot.rosters, self._rosters)
            if all(not roster for roster in self._rosters.values()):
                roster_from_state = await self.state_store.participant_rosters()
                self._rosters.update(roster_from_state)
        for week_index, matchups in enumerate(self.schedule, start=1):
            await self.simulate_week(week_index, matchups)
            if self.state_store is not None:
                await self.state_store.update_after_games(season=self.season_year, week=week_index)
        return list(self._games)

    def simulate_season_sync(self) -> List[GameLog]:
        return asyncio.run(self.simulate_season())

    def standings(self) -> Dict[int, TeamStanding]:
        return self._standings

    def player_stats(self) -> Dict[int, List[PlayerStatLine]]:
        return self._player_stats

    def games(self) -> List[GameLog]:
        return self._games

    def injuries(self) -> List[InjuryEvent]:
        return list(self._injury_history)

    def _get_team(self, team_id: int) -> TeamSeed:
        for team in self.teams:
            if team.id == team_id:
                return team
        raise KeyError(f"Unknown team id {team_id}")

    def _record_game(
        self,
        week_index: int,
        home_team: TeamSeed,
        away_team: TeamSeed,
        result: Dict[str, object],
        *,
        recap: Optional[str],
        narrative_facts: Optional[Dict[str, object]] = None,
        injuries: Optional[List[InjuryEvent]] = None,
    ) -> None:
        home_score = int(result["home_score"])
        away_score = int(result["away_score"])
        home_stats = result.get("player_stats", {}).get("home", [])  # type: ignore[union-attr]
        away_stats = result.get("player_stats", {}).get("away", [])  # type: ignore[union-attr]

        self._standings[home_team.id].record_result(home_score, away_score)
        self._standings[away_team.id].record_result(away_score, home_score)

        for stat in home_stats:
            self._player_stats[home_team.id].append(
                PlayerStatLine(
                    player=stat.get("name", "Unknown"),
                    summary=stat.get("line", ""),
                    week=week_index,
                )
            )
        for stat in away_stats:
            self._player_stats[away_team.id].append(
                PlayerStatLine(
                    player=stat.get("name", "Unknown"),
                    summary=stat.get("line", ""),
                    week=week_index,
                )
            )

        log = GameLog(
            week=week_index,
            home_team_id=home_team.id,
            away_team_id=away_team.id,
            home_score=home_score,
            away_score=away_score,
            win_prob=float(result.get("win_prob", 0.5)),
            drives=list(result.get("drives", [])),  # type: ignore[list-item]
            headline=str(result.get("headline", "")),
            recap=recap,
            narrative_facts=narrative_facts,
        )
        if injuries:
            for event in injuries:
                event.week = week_index
            log.injuries.extend(injuries)
            self._injury_history.extend(injuries)
        self._games.append(log)


def quick_season_from_ratings(
    ratings: Dict[int, float],
    *,
    names: Optional[Dict[int, str]] = None,
    abbrs: Optional[Dict[int, str]] = None,
    narrative_client: Optional[OpenRouterClient] = None,
    rng_seed: Optional[int] = None,
) -> SeasonSimulator:
    teams = [
        TeamSeed(
            id=team_id,
            name=(names or {}).get(team_id, f"Team {team_id}"),
            abbr=(abbrs or {}).get(team_id, f"T{team_id}"),
            rating=rating,
        )
        for team_id, rating in ratings.items()
    ]
    return SeasonSimulator(teams, narrative_client=narrative_client, rng_seed=rng_seed)
