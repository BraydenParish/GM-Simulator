"""Season orchestration utilities for the GM simulator."""

from __future__ import annotations

import asyncio
import random
from copy import deepcopy
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

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
    conference: Optional[str] = None
    division: Optional[str] = None


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

    @property
    def games_played(self) -> int:
        return self.wins + self.losses + self.ties

    @property
    def win_percentage(self) -> float:
        total = self.games_played
        if total == 0:
            return 0.0
        return (self.wins + 0.5 * self.ties) / total

    @property
    def point_differential(self) -> int:
        return self.points_for - self.points_against


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
    stage: str = "regular"
    round_name: Optional[str] = None


DIVISION_ORDER: Tuple[str, ...] = ("East", "North", "South", "West")
INTRA_CONFERENCE_ROTATION: Dict[str, List[Tuple[str, str]]] = {
    "AFC": [("East", "West"), ("North", "South")],
    "NFC": [("East", "West"), ("North", "South")],
}
cross_rotation_base: Dict[Tuple[str, str], Tuple[str, str]] = {
    ("AFC", "East"): ("NFC", "North"),
    ("AFC", "North"): ("NFC", "South"),
    ("AFC", "South"): ("NFC", "West"),
    ("AFC", "West"): ("NFC", "East"),
}
CROSS_CONFERENCE_ROTATION: Dict[Tuple[str, str], Tuple[str, str]] = dict(cross_rotation_base)
CROSS_CONFERENCE_ROTATION.update(
    {
        (other_conf, other_div): (conf, div)
        for (conf, div), (other_conf, other_div) in cross_rotation_base.items()
    }
)
INTERCONFERENCE_EXTRA: Dict[Tuple[str, str], Tuple[str, str]] = {
    ("AFC", "East"): ("NFC", "South"),
    ("AFC", "North"): ("NFC", "West"),
    ("AFC", "South"): ("NFC", "East"),
    ("AFC", "West"): ("NFC", "North"),
    ("NFC", "East"): ("AFC", "South"),
    ("NFC", "North"): ("AFC", "West"),
    ("NFC", "South"): ("AFC", "East"),
    ("NFC", "West"): ("AFC", "North"),
}


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
        self._postseason_games: List[GameLog] = []
        self._injury_history: List[InjuryEvent] = []
        self._conference_structure = self._structured_conference_map()
        if self._conference_structure:
            self.schedule = self._build_nfl_schedule(self._conference_structure)
        else:
            self.schedule = self._build_round_robin_schedule()
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
        self._head_to_head: Dict[frozenset[int], Dict[int, int]] = {}
        self._postseason_player_stats: Dict[int, List[PlayerStatLine]] = {
            team.id: [] for team in self.teams
        }

    def _build_round_robin_schedule(self) -> List[List[Tuple[int, int]]]:
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

    def _structured_conference_map(self) -> Optional[Dict[str, Dict[str, List[TeamSeed]]]]:
        structure: Dict[str, Dict[str, List[TeamSeed]]] = defaultdict(lambda: defaultdict(list))
        for team in self.teams:
            conference = (team.conference or "").upper()
            division = (team.division or "").title()
            if not conference or division not in DIVISION_ORDER:
                return None
            structure[conference][division].append(team)
        if len(structure) != 2:
            return None
        sorted_structure: Dict[str, Dict[str, List[TeamSeed]]] = {}
        for conference, divisions in structure.items():
            if len(divisions) != len(DIVISION_ORDER):
                return None
            sorted_structure[conference] = {}
            for division in DIVISION_ORDER:
                teams = divisions.get(division)
                if teams is None or len(teams) != 4:
                    return None
                sorted_structure[conference][division] = sorted(
                    teams,
                    key=lambda t: (-t.rating, t.id),
                )
        total = sum(
            len(teams) for divisions in sorted_structure.values() for teams in divisions.values()
        )
        if total != len(self.teams):
            return None
        return sorted_structure

    def _build_nfl_schedule(
        self, structure: Dict[str, Dict[str, List[TeamSeed]]]
    ) -> List[List[Tuple[int, int]]]:
        matchups: List[Tuple[int, int]] = []

        # Divisional home-and-away series
        for divisions in structure.values():
            for teams in divisions.values():
                matchups.extend(self._divisional_series(teams))

        # Primary intra-conference division rotations (4 games per opponent division)
        for conference, pairs in INTRA_CONFERENCE_ROTATION.items():
            conf_divisions = structure.get(conference)
            if not conf_divisions:
                continue
            for div_a, div_b in pairs:
                teams_a = conf_divisions.get(div_a)
                teams_b = conf_divisions.get(div_b)
                if teams_a and teams_b:
                    matchups.extend(self._full_division_series(teams_a, teams_b))

        # Secondary intra-conference games (two opponents from remaining divisions)
        for conference, divisions in structure.items():
            available = [division for division in DIVISION_ORDER if division in divisions]
            rotation_pairs = set()
            for pair in INTRA_CONFERENCE_ROTATION.get(conference, []):
                rotation_pairs.add(pair)
                rotation_pairs.add((pair[1], pair[0]))
            for idx, div_a in enumerate(available):
                for div_b in available[idx + 1 :]:
                    if (div_a, div_b) in rotation_pairs:
                        continue
                    matchups.extend(
                        self._ranked_pairings(
                            divisions[div_a],
                            divisions[div_b],
                            prefer_home_from_a=div_a < div_b,
                        )
                    )

        # Cross-conference division rotations (4 games per team)
        processed_cross: set[Tuple[Tuple[str, str], Tuple[str, str]]] = set()
        for (conference, division), opponent in CROSS_CONFERENCE_ROTATION.items():
            conf_divisions = structure.get(conference)
            other_divisions = structure.get(opponent[0])
            if not conf_divisions or not other_divisions:
                continue
            key = tuple(sorted(((conference, division), opponent)))
            if key in processed_cross:
                continue
            teams_a = conf_divisions.get(division)
            teams_b = other_divisions.get(opponent[1])
            if teams_a and teams_b:
                processed_cross.add(key)
                matchups.extend(self._full_division_series(teams_a, teams_b))

        # 17th game cross-conference pairings aligned by divisional ranking
        processed_extra: set[Tuple[Tuple[str, str], Tuple[str, str]]] = set()
        for (conference, division), opponent in INTERCONFERENCE_EXTRA.items():
            conf_divisions = structure.get(conference)
            other_divisions = structure.get(opponent[0])
            if not conf_divisions or not other_divisions:
                continue
            key = tuple(sorted(((conference, division), opponent)))
            if key in processed_extra:
                continue
            teams_a = conf_divisions.get(division)
            teams_b = other_divisions.get(opponent[1])
            if teams_a and teams_b:
                processed_extra.add(key)
                prefer_home = (conference, division) <= opponent
                matchups.extend(
                    self._ranked_pairings(
                        teams_a,
                        teams_b,
                        prefer_home_from_a=prefer_home,
                    )
                )

        counts: Dict[int, int] = defaultdict(int)
        for home, away in matchups:
            counts[home] += 1
            counts[away] += 1
        if any(count != 17 for count in counts.values()):
            raise ValueError("Failed to build 17-game schedule for provided teams")

        return self._distribute_matchups(matchups, weeks_count=18)

    def _divisional_series(self, teams: Sequence[TeamSeed]) -> List[Tuple[int, int]]:
        fixtures: List[Tuple[int, int]] = []
        ordered = list(teams)
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                home = ordered[i]
                away = ordered[j]
                fixtures.append((home.id, away.id))
                fixtures.append((away.id, home.id))
        return fixtures

    def _full_division_series(
        self, division_a: Sequence[TeamSeed], division_b: Sequence[TeamSeed]
    ) -> List[Tuple[int, int]]:
        fixtures: List[Tuple[int, int]] = []
        for idx_a, team_a in enumerate(division_a):
            for idx_b, team_b in enumerate(division_b):
                if (idx_a + idx_b) % 2 == 0:
                    fixtures.append((team_a.id, team_b.id))
                else:
                    fixtures.append((team_b.id, team_a.id))
        return fixtures

    def _ranked_pairings(
        self,
        division_a: Sequence[TeamSeed],
        division_b: Sequence[TeamSeed],
        *,
        prefer_home_from_a: bool,
    ) -> List[Tuple[int, int]]:
        fixtures: List[Tuple[int, int]] = []
        limit = min(len(division_a), len(division_b))
        for idx in range(limit):
            team_a = division_a[idx]
            team_b = division_b[idx]
            home_is_a = prefer_home_from_a if idx % 2 == 0 else not prefer_home_from_a
            if home_is_a:
                fixtures.append((team_a.id, team_b.id))
            else:
                fixtures.append((team_b.id, team_a.id))
        return fixtures

    def _distribute_matchups(
        self, matchups: List[Tuple[int, int]], *, weeks_count: int
    ) -> List[List[Tuple[int, int]]]:
        fixtures = matchups[:]
        self._random.shuffle(fixtures)
        weeks: List[List[Tuple[int, int]]] = [[] for _ in range(weeks_count)]
        usage: List[set[int]] = [set() for _ in range(weeks_count)]
        for home, away in fixtures:
            placed = False
            for week_index in range(len(weeks)):
                if home not in usage[week_index] and away not in usage[week_index]:
                    weeks[week_index].append((home, away))
                    usage[week_index].update({home, away})
                    placed = True
                    break
            if not placed:
                weeks.append([(home, away)])
                usage.append({home, away})
        return [week for week in weeks if week]

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

    def postseason_games(self) -> List[GameLog]:
        return self._postseason_games

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
        stage: str = "regular",
        round_name: Optional[str] = None,
    ) -> None:
        home_score = int(result["home_score"])
        away_score = int(result["away_score"])
        home_stats = result.get("player_stats", {}).get("home", [])  # type: ignore[union-attr]
        away_stats = result.get("player_stats", {}).get("away", [])  # type: ignore[union-attr]

        if stage == "regular":
            self._standings[home_team.id].record_result(home_score, away_score)
            self._standings[away_team.id].record_result(away_score, home_score)
            key = frozenset({home_team.id, away_team.id})
            series = self._head_to_head.setdefault(key, defaultdict(int))
            if home_score > away_score:
                series[home_team.id] += 1
            elif away_score > home_score:
                series[away_team.id] += 1

        stat_target = self._player_stats if stage == "regular" else self._postseason_player_stats

        for stat in home_stats:
            stat_target[home_team.id].append(
                PlayerStatLine(
                    player=stat.get("name", "Unknown"),
                    summary=stat.get("line", ""),
                    week=week_index,
                )
            )
        for stat in away_stats:
            stat_target[away_team.id].append(
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
            stage=stage,
            round_name=round_name,
        )
        if injuries:
            log.injuries.extend(injuries)
            self._injury_history.extend(injuries)
        if stage == "regular":
            self._games.append(log)
        else:
            self._postseason_games.append(log)

    def _head_to_head_wins(self, team_id: int, opponents: Sequence[int]) -> int:
        wins = 0
        for opponent in opponents:
            if opponent == team_id:
                continue
            key = frozenset({team_id, opponent})
            record = self._head_to_head.get(key)
            if not record:
                continue
            wins += record.get(team_id, 0)
        return wins

    def _ranking_key(
        self, team_id: int, peer_group: Sequence[int]
    ) -> Tuple[float, int, int, int, int, int]:
        standing = self._standings[team_id]
        head_to_head = self._head_to_head_wins(team_id, peer_group)
        return (
            standing.win_percentage,
            head_to_head,
            standing.point_differential,
            standing.points_for,
            standing.wins,
            -team_id,
        )

    def ranked_team_ids(self) -> List[int]:
        by_record: Dict[Tuple[int, int, int], List[int]] = defaultdict(list)
        for team_id, standing in self._standings.items():
            by_record[(standing.wins, standing.losses, standing.ties)].append(team_id)
        ordered_records = sorted(by_record.keys(), reverse=True)
        ranking: List[int] = []
        for record in ordered_records:
            group = by_record[record]
            if len(group) == 1:
                ranking.extend(group)
                continue
            group_sorted = sorted(
                group,
                key=lambda tid: self._ranking_key(tid, group),
                reverse=True,
            )
            buckets: Dict[Tuple[float, int, int, int, int], List[int]] = defaultdict(list)
            for team_id in group_sorted:
                bucket_key = self._ranking_key(team_id, group)[:-1]
                buckets[bucket_key].append(team_id)
            for bucket_key in sorted(buckets.keys(), reverse=True):
                teams = buckets[bucket_key]
                if len(teams) == 1:
                    ranking.append(teams[0])
                else:
                    shuffled = teams[:]
                    self._random.shuffle(shuffled)
                    ranking.extend(shuffled)
        return ranking

    def ranked_teams(self) -> List[TeamSeed]:
        return [self._get_team(team_id) for team_id in self.ranked_team_ids()]

    async def simulate_playoffs(self, seeds: int = 4) -> List[GameLog]:
        if seeds < 2:
            raise ValueError("At least two seeds are required for playoffs")
        ranked = self.ranked_team_ids()
        if len(ranked) < 2:
            return []
        bracket = ranked[: min(seeds, len(ranked))]
        if len(bracket) < 2:
            return []
        postseason_logs: List[GameLog] = []
        current = bracket
        playoff_week = len(self.schedule) + 1
        while len(current) > 1:
            matchups: List[Tuple[int, int]] = []
            for i in range(len(current) // 2):
                matchups.append((current[i], current[-(i + 1)]))
            winners: List[int] = []
            teams_remaining = len(current)
            if teams_remaining == 2:
                round_name = "Super Bowl"
            elif teams_remaining == 4:
                round_name = "Conference Championship"
            elif teams_remaining == 8:
                round_name = "Divisional"
            else:
                round_name = "Wild Card"
            for home_id, away_id in matchups:
                home_team = self._get_team(home_id)
                away_team = self._get_team(away_id)
                result = simulate_game(
                    home_id,
                    away_id,
                    home_team.rating,
                    away_team.rating,
                    home_roster=self._rosters.get(home_id),
                    away_roster=self._rosters.get(away_id),
                    seed=self._random.randint(0, 1_000_000),
                )
                self._record_game(
                    playoff_week,
                    home_team,
                    away_team,
                    result,
                    recap=None,
                    narrative_facts=None,
                    injuries=None,
                    stage="postseason",
                    round_name=round_name,
                )
                log = self._postseason_games[-1]
                postseason_logs.append(log)
                if log.home_score >= log.away_score:
                    winners.append(home_id)
                else:
                    winners.append(away_id)
            current = winners
            playoff_week += 1
        return postseason_logs


def quick_season_from_ratings(
    ratings: Dict[int, float],
    *,
    names: Optional[Dict[int, str]] = None,
    abbrs: Optional[Dict[int, str]] = None,
    narrative_client: Optional[OpenRouterClient] = None,
    rng_seed: Optional[int] = None,
    conferences: Optional[Dict[int, str]] = None,
    divisions: Optional[Dict[int, str]] = None,
) -> SeasonSimulator:
    teams = [
        TeamSeed(
            id=team_id,
            name=(names or {}).get(team_id, f"Team {team_id}"),
            abbr=(abbrs or {}).get(team_id, f"T{team_id}"),
            rating=rating,
            conference=(conferences or {}).get(team_id),
            division=(divisions or {}).get(team_id),
        )
        for team_id, rating in ratings.items()
    ]
    return SeasonSimulator(teams, narrative_client=narrative_client, rng_seed=rng_seed)
