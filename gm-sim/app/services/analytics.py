"""Advanced analytics helpers for simulated games.

These utilities operate on the lightweight drive data produced by the core
simulation engine so we can surface modern metrics such as estimated points
added (EPA) and a win probability track without introducing heavyweight
dependencies.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, MutableMapping, Tuple


_RESULT_POINTS: Dict[str, int] = {
    "TD": 7,
    "TOUCHDOWN": 7,
    "FG": 3,
    "FIELD GOAL": 3,
    "SAFETY": 2,
    "TURNOVER": -3,
    "INT": -3,
    "INTERCEPTION": -3,
    "FUMBLE": -3,
    "MISSED FG": -1,
    "BLOCKED FG": -1,
    "DOWNS": -2,
    "PUNT": 0,
    "KICKOFF": 0,
    "END HALF": 0,
    "END GAME": 0,
}

_EXPECTED_POINTS_BASELINE = 2.3


def _normalize_result(result: str | None) -> str:
    if not result:
        return ""
    return result.strip().upper()


def _points_for_result(result: str | None) -> int:
    normalized = _normalize_result(result)
    return _RESULT_POINTS.get(normalized, 0)


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def compute_drive_analytics(
    *,
    drives: Iterable[MutableMapping[str, Any]],
    home_score: int,
    away_score: int,
) -> Dict[str, Any]:
    """Return EPA + win probability estimates for each simulated drive.

    The goal is to provide modern-feeling analytics without requiring the raw
    play-by-play context a real NFL dataset would expose. We apply a simple
    expected-points baseline and update a logistic win probability curve after
    every recorded drive.
    """

    drive_list: List[MutableMapping[str, Any]] = [dict(drive) for drive in drives]
    if not drive_list:
        return {
            "drives": [],
            "summary": {
                "home": {
                    "final_score": home_score,
                    "total_epa": 0.0,
                    "success_rate": 0.0,
                },
                "away": {
                    "final_score": away_score,
                    "total_epa": 0.0,
                    "success_rate": 0.0,
                },
                "explosive_plays": 0,
            },
        }

    total_minutes = sum(float(drive.get("minutes", 0.0) or 0.0) for drive in drive_list)
    if total_minutes <= 0:
        total_minutes = 60.0
    total_minutes = max(total_minutes, 30.0)

    elapsed_minutes = 0.0
    home_points = 0
    away_points = 0
    analytics: List[Dict[str, Any]] = []
    summary: Dict[str, Dict[str, float]] = {
        "home": {"total_epa": 0.0, "successes": 0.0, "drives": 0.0},
        "away": {"total_epa": 0.0, "successes": 0.0, "drives": 0.0},
    }
    explosive_plays = 0

    for index, drive in enumerate(drive_list):
        team = str(drive.get("team", "home"))
        result = drive.get("result")
        yards = int(drive.get("yards", 0) or 0)
        minutes = float(drive.get("minutes", 0.0) or 0.0)

        points = _points_for_result(result)
        expected_points = _EXPECTED_POINTS_BASELINE
        epa = round(points - expected_points, 2)

        if team.lower() == "home":
            home_points += max(points, 0)
            summary_entry = summary["home"]
        else:
            away_points += max(points, 0)
            summary_entry = summary["away"]

        summary_entry["total_epa"] += epa
        summary_entry["drives"] += 1
        if epa > 0:
            summary_entry["successes"] += 1

        elapsed_minutes += max(minutes, 0.0)
        elapsed_fraction = min(max(elapsed_minutes / total_minutes, 0.0), 1.0)
        score_diff = home_points - away_points
        win_prob_home = round(
            _sigmoid(0.4 * score_diff + 0.4 * (0.5 - elapsed_fraction)), 4
        )

        if yards >= 40 or _normalize_result(result) in {"TD", "TOUCHDOWN", "TURNOVER"}:
            explosive_plays += 1

        analytics.append(
            {
                "drive_index": index,
                "team": team,
                "result": result,
                "yards": yards,
                "minutes": minutes if minutes else None,
                "points": points,
                "expected_points": round(expected_points, 2),
                "epa": epa,
                "home_score_running": home_points,
                "away_score_running": away_points,
                "home_win_prob": win_prob_home,
            }
        )

    home_summary = summary["home"]
    away_summary = summary["away"]

    def _finalize(entry: Dict[str, float], final_score: int) -> Dict[str, float]:
        drives_played = entry["drives"] or 1.0
        return {
            "final_score": final_score,
            "total_epa": round(entry["total_epa"], 2),
            "success_rate": round(entry["successes"] / drives_played, 3),
        }

    return {
        "drives": analytics,
        "summary": {
            "home": _finalize(home_summary, home_score),
            "away": _finalize(away_summary, away_score),
            "explosive_plays": explosive_plays,
        },
    }


def attach_game_analytics(game_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of ``game_payload`` augmented with analytics metadata."""

    drives = game_payload.get("drives", [])
    home_score = int(game_payload.get("home_score", 0))
    away_score = int(game_payload.get("away_score", 0))
    analytics = compute_drive_analytics(
        drives=[dict(drive) for drive in drives],
        home_score=home_score,
        away_score=away_score,
    )
    enriched = dict(game_payload)
    enriched.setdefault("analytics", analytics)
    return enriched
