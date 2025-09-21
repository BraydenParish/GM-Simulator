import random
from typing import Dict, Iterable, List, Sequence

from app.models import Player
from app.services.elo import win_prob

_STAT_KEYS = [
    "passing_yards",
    "passing_tds",
    "interceptions",
    "rushing_yards",
    "rushing_tds",
    "receptions",
    "receiving_yards",
    "receiving_tds",
    "sacks",
]


def _init_stat_line() -> Dict[str, int]:
    return {key: 0 for key in _STAT_KEYS}


def _pos_match(player: Player | None, positions: Sequence[str]) -> bool:
    if not player or not player.pos:
        return False
    return player.pos.upper() in {pos.upper() for pos in positions}


def _select_players(
    roster: Iterable[Player], positions: Sequence[str], limit: int
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
    candidates: List[Player] = [
        player for player in sorted_roster if _pos_match(player, positions)
    ]

    if len(candidates) < limit:
        for player in sorted_roster:
            if player in candidates:
                continue
            candidates.append(player)
            if len(candidates) >= limit:
                break

    unique: List[Player] = []
    seen: set[int] = set()
    for player in candidates:
        if player.id in seen:
            continue
        unique.append(player)
        seen.add(player.id)
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

    qbs = _select_players(roster, ["QB"], limit=1)
    rbs = _select_players(roster, ["RB", "HB", "FB"], limit=2)
    receivers = _select_players(roster, ["WR", "TE"], limit=3)
    defenders = _select_players(roster, ["EDGE", "DE", "OLB", "DL", "LB"], limit=2)

    if qbs:
        qb = qbs[0]
        add_line(
            qb,
            {
                "passing_yards": random.randint(210, 340),
                "passing_tds": random.randint(1, 4),
                "interceptions": random.randint(0, 2),
            },
        )
        add_line(
            qb,
            {
                "rushing_yards": random.randint(15, 60),
                "rushing_tds": random.randint(0, 2),
            },
        )

    for idx, rb in enumerate(rbs):
        add_line(
            rb,
            {
                "rushing_yards": (
                    random.randint(60, 130) if idx == 0 else random.randint(25, 80)
                ),
                "rushing_tds": random.randint(0, 2 if idx == 0 else 1),
                "receptions": (
                    random.randint(1, 5) if idx == 0 else random.randint(0, 3)
                ),
                "receiving_yards": (
                    random.randint(15, 50) if idx == 0 else random.randint(5, 30)
                ),
            },
        )

    for idx, receiver in enumerate(receivers):
        add_line(
            receiver,
            {
                "receptions": (
                    random.randint(5, 11)
                    if idx == 0
                    else random.randint(3, 8) if idx == 1 else random.randint(2, 6)
                ),
                "receiving_yards": (
                    random.randint(70, 170)
                    if idx == 0
                    else random.randint(40, 110) if idx == 1 else random.randint(25, 75)
                ),
                "receiving_tds": random.randint(0, 2 if idx < 2 else 1),
            },
        )

    for idx, defender in enumerate(defenders):
        add_line(
            defender,
            {
                "sacks": random.randint(1, 3) if idx == 0 else random.randint(0, 2),
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

    box = {
        "player_stats": player_stats,
    }
    return {
        "home_score": home_pts,
        "away_score": away_pts,
        "win_prob": prob,
        "box": box,
        "player_stats": player_stats,
    }
