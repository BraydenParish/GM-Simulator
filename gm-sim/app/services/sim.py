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


def _select_player(roster: Iterable[Player], positions: Sequence[str]) -> Player | None:
    candidates: List[Player] = [
        player for player in roster if _pos_match(player, positions)
    ]
    candidates.sort(key=lambda pl: pl.ovr or 0, reverse=True)
    return candidates[0] if candidates else None


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

    qb = _select_player(roster, ["QB"])
    rb = _select_player(roster, ["RB", "HB"])
    wr = _select_player(roster, ["WR", "TE"])
    edge = _select_player(roster, ["EDGE", "DE", "OLB"]) or _select_player(
        roster, ["LB"]
    )

    if qb:
        add_line(
            qb,
            {
                "passing_yards": random.randint(180, 320),
                "passing_tds": random.randint(1, 4),
                "interceptions": random.randint(0, 2),
            },
        )
        add_line(
            qb,
            {
                "rushing_yards": random.randint(10, 40),
                "rushing_tds": random.randint(0, 1),
            },
        )

    if rb:
        add_line(
            rb,
            {
                "rushing_yards": random.randint(50, 130),
                "rushing_tds": random.randint(0, 2),
                "receptions": random.randint(1, 4),
                "receiving_yards": random.randint(10, 40),
            },
        )

    if wr:
        add_line(
            wr,
            {
                "receptions": random.randint(4, 10),
                "receiving_yards": random.randint(60, 160),
                "receiving_tds": random.randint(0, 2),
            },
        )

    if edge:
        add_line(
            edge,
            {
                "sacks": random.randint(0, 3),
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
