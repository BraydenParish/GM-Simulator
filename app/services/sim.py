import random
from typing import Dict, List, Optional, Sequence

from app.services.elo import win_prob
from app.services.injuries import PlayerParticipation

DRIVE_RESULTS = [
    "TD",
    "FG",
    "Punt",
    "Turnover",
]
DRIVE_WEIGHTS = [0.25, 0.2, 0.4, 0.15]


def _generate_drive(team_label: str) -> Dict[str, int | str | float]:
    result = random.choices(DRIVE_RESULTS, weights=DRIVE_WEIGHTS, k=1)[0]
    yards = max(0, int(random.gauss(32, 18)))
    duration = max(1.0, random.gauss(2.8, 0.9))
    return {
        "team": team_label,
        "result": result,
        "yards": yards,
        "minutes": round(duration, 1),
    }


def _headline(home_score: int, away_score: int) -> str:
    margin = abs(home_score - away_score)
    if margin <= 3:
        return "Nail-biter comes down to the final drive"
    if margin >= 17:
        return "Statement win in all three phases"
    return "Solid all-around performance"


def _fallback_lines(prefix: str) -> List[Dict[str, str | int]]:
    qb_stats = {
        "player_id": 0,
        "name": f"{prefix} QB",
        "line": f"{random.randint(18, 30)}/{random.randint(28, 40)} for {random.randint(210, 345)} yds"
        f" and {random.randint(1, 4)} TDs",
    }
    rb_stats = {
        "player_id": 0,
        "name": f"{prefix} RB",
        "line": f"{random.randint(12, 24)} carries for {random.randint(45, 130)} yds",
    }
    wr_stats = {
        "player_id": 0,
        "name": f"{prefix} WR",
        "line": f"{random.randint(5, 10)} catches for {random.randint(70, 160)} yds",
    }
    return [qb_stats, rb_stats, wr_stats]


def _pick_participant(
    roster: Sequence[PlayerParticipation] | None,
    position: str,
    fallback: Optional[PlayerParticipation],
) -> Optional[PlayerParticipation]:
    if not roster:
        return fallback
    position_upper = position.upper()
    for participant in roster:
        if participant.position.upper() == position_upper:
            return participant
    return fallback or (roster[0] if roster else None)


def _player_lines(
    prefix: str, roster: Sequence[PlayerParticipation] | None
) -> List[Dict[str, str | int]]:
    if not roster:
        return _fallback_lines(prefix)

    qb = _pick_participant(roster, "QB", roster[0])
    rb = _pick_participant(roster, "RB", roster[0])
    wr = _pick_participant(roster, "WR", roster[0])

    lines: List[Dict[str, str | int]] = []
    for participant, template in (
        (qb, "QB"),
        (rb, "RB"),
        (wr, "WR"),
    ):
        if participant is None:
            continue
        name = participant.player_name or f"Player {participant.player_id}"
        if template == "QB":
            stat_line = (
                f"{random.randint(18, 30)}/{random.randint(28, 40)} for {random.randint(210, 345)} yds"
                f" and {random.randint(1, 4)} TDs"
            )
        elif template == "RB":
            stat_line = f"{random.randint(12, 24)} carries for {random.randint(45, 130)} yds"
        else:
            stat_line = f"{random.randint(5, 10)} catches for {random.randint(70, 160)} yds"
        lines.append({"player_id": participant.player_id, "name": name, "line": stat_line})

    if not lines:
        return _fallback_lines(prefix)
    return lines


def simulate_game(
    home_team_id: int,
    away_team_id: int,
    home_rating: float,
    away_rating: float,
    *,
    home_roster: Sequence[PlayerParticipation] | None = None,
    away_roster: Sequence[PlayerParticipation] | None = None,
    seed: int | None = None,
):
    if seed is not None:
        random.seed(seed)
    prob = win_prob(home_rating, away_rating)
    exp_pts = 45
    home_pts = max(6, int(exp_pts * prob + random.gauss(0, 6)))
    away_pts = max(3, int(exp_pts * (1 - prob) + random.gauss(0, 6)))

    total_drives = random.randint(20, 26)
    drives = []
    home_scoring = 0
    away_scoring = 0
    for idx in range(total_drives):
        team = "home" if idx % 2 == 0 else "away"
        drive = _generate_drive(team)
        if drive["result"] == "TD":
            if team == "home":
                home_scoring += 7
            else:
                away_scoring += 7
        elif drive["result"] == "FG":
            if team == "home":
                home_scoring += 3
            else:
                away_scoring += 3
        drives.append(drive)

    score_adjust = home_pts - home_scoring
    if score_adjust > 0:
        drives.append({"team": "home", "result": "FG", "yards": 38, "minutes": 1.1})
        home_scoring += 3
    score_adjust = away_pts - away_scoring
    if score_adjust > 0:
        drives.append({"team": "away", "result": "FG", "yards": 34, "minutes": 1.0})
        away_scoring += 3

    box = {
        "home_qb": {
            "yds": random.randint(180, 360),
            "td": random.randint(1, 4),
            "int": random.randint(0, 2),
        },
        "away_qb": {
            "yds": random.randint(180, 330),
            "td": random.randint(1, 3),
            "int": random.randint(0, 3),
        },
        "home_wr": {"yds": random.randint(60, 150), "td": random.randint(0, 3)},
        "away_wr": {"yds": random.randint(60, 150), "td": random.randint(0, 3)},
        "home_edge": {"sacks": random.randint(0, 4)},
        "away_edge": {"sacks": random.randint(0, 4)},
    }

    return {
        "home_score": home_pts,
        "away_score": away_pts,
        "win_prob": prob,
        "box": box,
        "drives": drives,
        "headline": _headline(home_pts, away_pts),
        "player_stats": {
            "home": _player_lines("Home", home_roster),
            "away": _player_lines("Away", away_roster),
        },
    }
