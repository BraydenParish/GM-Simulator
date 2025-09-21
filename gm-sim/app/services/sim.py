import random
from typing import Dict, Iterable, List, Sequence, Set

from app.models import Player
from app.services.elo import win_prob

_STAT_KEYS = [
    "passing_attempts",
    "passing_completions",
    "passing_yards",
    "passing_tds",
    "interceptions",
    "rushing_attempts",
    "rushing_yards",
    "rushing_tds",
    "receptions",
    "targets",
    "receiving_yards",
    "receiving_tds",
    "fumbles",
    "sacks",
    "tackles",
    "tackles_for_loss",
    "passes_defended",
    "def_interceptions",
    "forced_fumbles",
    "defensive_tds",
    "field_goals_made",
    "field_goals_attempted",
    "extra_points_made",
    "extra_points_attempted",
    "punts",
    "punt_yards",
    "kick_return_yards",
    "punt_return_yards",
    "return_tds",
]


def _init_stat_line() -> Dict[str, int]:
    return {key: 0 for key in _STAT_KEYS}


def _pos_match(player: Player | None, positions: Sequence[str]) -> bool:
    if not player or not player.pos:
        return False
    return player.pos.upper() in {pos.upper() for pos in positions}


def _triangular_int(low: int, high: int, mode: int) -> int:
    """Return an integer sampled from a triangular distribution."""

    return int(round(random.triangular(low, high, mode)))


def _select_players(
    roster: Iterable[Player],
    positions: Sequence[str],
    limit: int,
    *,
    exclude: Set[int] | None = None,
) -> List[Player]:
    """Select players for a role with positional fallbacks.

    The simulator prefers players who match the requested positions, but when a
    roster is thin (common with test data or early franchise states) we fall
    back to the best remaining players so every team still records a full stat
    line.  The returned list is ordered from highest to lowest overall rating
    and contains at most ``limit`` unique players.
    """

    sorted_roster: List[Player] = sorted(
        roster, key=lambda pl: pl.ovr or 0, reverse=True
    )
    exclude_ids: Set[int] = set(exclude or set())
    candidates: List[Player] = [
        player
        for player in sorted_roster
        if _pos_match(player, positions) and (player.id not in exclude_ids)
    ]

    if len(candidates) < limit:
        for player in sorted_roster:
            if player.id in exclude_ids or player in candidates:
                continue
            candidates.append(player)
            if len(candidates) >= limit:
                break

    if len(candidates) < limit and exclude_ids:
        for player in sorted_roster:
            if player in candidates:
                continue
            candidates.append(player)
            if len(candidates) >= limit:
                break

    unique: List[Player] = []
    seen: Set[int] = set()
    for player in candidates:
        player_id = player.id if player.id is not None else id(player)
        if player_id in seen:
            continue
        unique.append(player)
        seen.add(player_id)
        if len(unique) >= limit:
            break

    return unique


def _build_team_player_stats(
    team_id: int, roster: List[Player]
) -> Dict[int, Dict[str, int]]:
    stats: Dict[int, Dict[str, int]] = {}

    def add_line(player: Player | None, updates: Dict[str, int]) -> None:
        if not player:
            return
        line = stats.setdefault(player.id, _init_stat_line())
        for key, value in updates.items():
            line[key] += value

    used_primary: Set[int] = set()
    qbs = _select_players(roster, ["QB"], limit=1, exclude=used_primary)
    used_primary.update(player.id for player in qbs if player.id is not None)

    rbs = _select_players(roster, ["RB", "HB", "FB"], limit=2, exclude=used_primary)
    used_primary.update(player.id for player in rbs if player.id is not None)

    receivers = _select_players(roster, ["WR", "TE"], limit=3, exclude=used_primary)
    used_primary.update(player.id for player in receivers if player.id is not None)

    defenders = _select_players(
        roster,
        ["EDGE", "DE", "OLB", "DL", "LB", "CB", "S", "FS", "SS", "ILB", "MLB"],
        limit=4,
        exclude=used_primary,
    )
    used_primary.update(player.id for player in defenders if player.id is not None)

    kicker = _select_players(roster, ["K"], limit=1, exclude=used_primary)
    used_primary.update(player.id for player in kicker if player.id is not None)

    punter = _select_players(roster, ["P"], limit=1, exclude=used_primary)
    returners = _select_players(roster, ["WR", "RB", "CB"], limit=2)

    if qbs:
        qb = qbs[0]
        attempts = _triangular_int(28, 43, 35)
        completion_pct = random.uniform(0.58, 0.72)
        completions = max(12, int(round(attempts * completion_pct)))
        completions = min(completions, attempts)
        yards_per_attempt = random.uniform(6.5, 8.6)
        passing_yards = int(round(attempts * yards_per_attempt))
        rushing_attempts = _triangular_int(2, 7, 3)
        rushing_yards = _triangular_int(5, 55, 18)
        add_line(
            qb,
            {
                "passing_attempts": attempts,
                "passing_completions": completions,
                "passing_yards": passing_yards,
                "passing_tds": _triangular_int(1, 5, 2),
                "interceptions": _triangular_int(0, 3, 1),
                "rushing_attempts": rushing_attempts,
                "rushing_yards": rushing_yards,
                "rushing_tds": random.randint(0, 1),
                "fumbles": random.choice([0, 0, 1]),
            },
        )

    for idx, rb in enumerate(rbs):
        attempts = (
            _triangular_int(14, 24, 18) if idx == 0 else _triangular_int(6, 14, 9)
        )
        rushing_yards = int(round(attempts * random.uniform(3.7, 5.5)))
        targets = _triangular_int(3, 7, 4) if idx == 0 else _triangular_int(1, 4, 2)
        receptions = min(
            targets,
            _triangular_int(max(0, targets - 2), targets, max(1, targets - 1)),
        )
        add_line(
            rb,
            {
                "rushing_attempts": attempts,
                "rushing_yards": rushing_yards,
                "rushing_tds": random.randint(0, 2 if idx == 0 else 1),
                "receptions": receptions,
                "targets": targets,
                "receiving_yards": int(round(receptions * random.uniform(6.0, 9.0))),
                "receiving_tds": random.randint(0, 1 if idx == 0 else 0),
                "fumbles": random.choice([0, 0, 0, 1]),
            },
        )

    for idx, receiver in enumerate(receivers):
        base_targets = [11, 8, 6]
        targets = (
            _triangular_int(
                max(4, base_targets[idx] - 3), base_targets[idx] + 2, base_targets[idx]
            )
            if idx < len(base_targets)
            else _triangular_int(4, 7, 5)
        )
        receptions = min(
            targets,
            _triangular_int(max(2, targets - 4), targets, max(3, targets - 2)),
        )
        yard_multiplier = [12.5, 11.0, 9.0]
        yards = int(
            round(
                receptions
                * random.uniform(
                    yard_multiplier[idx] - 1.5 if idx < len(yard_multiplier) else 8.0,
                    yard_multiplier[idx] + 1.5 if idx < len(yard_multiplier) else 10.0,
                )
            )
        )
        add_line(
            receiver,
            {
                "receptions": receptions,
                "targets": targets,
                "receiving_yards": yards,
                "receiving_tds": random.randint(0, 2 if idx < 2 else 1),
                "fumbles": random.choice([0, 0, 1]) if idx == 2 else 0,
            },
        )

    for idx, defender in enumerate(defenders):
        tackles = _triangular_int(4, 12, 7 if idx < 2 else 5)
        tackles_for_loss = _triangular_int(0, 3, 1 if idx < 2 else 1)
        sacks = _triangular_int(0, 3, 1 if idx == 0 else 0)
        def_ints = random.choice([0, 0, 0, 1])
        passes_defended = max(def_ints, _triangular_int(0, 3, 1))
        add_line(
            defender,
            {
                "sacks": sacks,
                "tackles": tackles,
                "tackles_for_loss": tackles_for_loss,
                "def_interceptions": def_ints,
                "passes_defended": passes_defended,
                "forced_fumbles": random.choice([0, 0, 1]),
                "defensive_tds": 1 if def_ints and random.random() < 0.15 else 0,
            },
        )

    if kicker:
        k = kicker[0]
        fg_att = _triangular_int(1, 5, 3)
        fg_made = min(fg_att, _triangular_int(max(0, fg_att - 1), fg_att, fg_att))
        xp_att = _triangular_int(2, 6, 4)
        xp_made = min(xp_att, xp_att - random.choice([0, 0, 0, 1]))
        add_line(
            k,
            {
                "field_goals_attempted": fg_att,
                "field_goals_made": fg_made,
                "extra_points_attempted": xp_att,
                "extra_points_made": xp_made,
            },
        )

    if punter:
        p = punter[0]
        punts = _triangular_int(3, 7, 5)
        punt_yards = punts * _triangular_int(42, 52, 46)
        add_line(
            p,
            {
                "punts": punts,
                "punt_yards": punt_yards,
            },
        )

    for idx, returner in enumerate(returners):
        kick_yards = _triangular_int(25, 120, 62)
        punt_yards = _triangular_int(0, 60, 18 if idx == 0 else 12)
        add_line(
            returner,
            {
                "kick_return_yards": kick_yards,
                "punt_return_yards": punt_yards,
                "return_tds": 1 if random.random() < 0.04 else 0,
                "fumbles": random.choice([0, 0, 1]),
            },
        )

    return stats


def simulate_game(
    home_team_id: int,
    away_team_id: int,
    home_rating: float,
    away_rating: float,
    *,
    seed: int | None = None,
    home_roster: List[Player] | None = None,
    away_roster: List[Player] | None = None,
):
    if seed is not None:
        random.seed(seed)
    prob = win_prob(home_rating, away_rating)
    exp_pts = 45
    home_pts = int(exp_pts * prob + random.gauss(0, 3))
    away_pts = int(exp_pts * (1 - prob) + random.gauss(0, 3))

    player_stats: List[Dict[str, object]] = []
    team_totals: Dict[int, Dict[str, int]] = {}
    for team_id, roster in (
        (home_team_id, home_roster or []),
        (away_team_id, away_roster or []),
    ):
        team_stats = _build_team_player_stats(team_id, list(roster))
        for player_id, stat_line in team_stats.items():
            player_stats.append(
                {
                    "player_id": player_id,
                    "team_id": team_id,
                    "stats": stat_line,
                }
            )
            team_line = team_totals.setdefault(team_id, {})
            for key, value in stat_line.items():
                team_line[key] = team_line.get(key, 0) + value

    team_totals_payload = [
        {"team_id": team_id, "stats": stat_line}
        for team_id, stat_line in sorted(team_totals.items())
    ]

    box = {
        "player_stats": player_stats,
        "team_totals": team_totals_payload,
    }
    return {
        "home_score": home_pts,
        "away_score": away_pts,
        "win_prob": prob,
        "box": box,
        "player_stats": player_stats,
        "team_totals": team_totals,
    }
