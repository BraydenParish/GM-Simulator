"""Load and blend player ratings from Madden and PFF data sources."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

OFFENSE_POSITIONS = {"QB", "RB", "WR", "TE", "OT", "OG", "C", "IOL"}
DEFENSE_POSITIONS = {"EDGE", "IDL", "DT", "LB", "CB", "S", "FS", "SS"}


@dataclass
class PlayerRating:
    player_id: int
    name: str
    pos: str
    team_abbr: str
    overall: float
    madden_ovr: float
    pff_grade: Optional[float]
    traits: Dict[str, float]


def _read_csv(path: Path) -> Iterable[Dict[str, str]]:
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            yield row


def load_madden25(path: Path) -> Dict[int, Dict[str, str]]:
    """Return the Madden 25 ratings keyed by player id."""

    data: Dict[int, Dict[str, str]] = {}
    for row in _read_csv(path):
        try:
            player_id = int(row["player_id"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid player_id in {path}: {row}") from exc
        data[player_id] = row
    return data


def load_pff_grades(path: Path, season: Optional[int] = None) -> Dict[int, Dict[str, str]]:
    """Return the latest PFF grades keyed by player id."""

    data: Dict[int, Dict[str, str]] = {}
    for row in _read_csv(path):
        if season is not None:
            try:
                season_val = int(row.get("season", 0))
            except (TypeError, ValueError):
                continue
            if season_val != season:
                continue
        try:
            player_id = int(row["player_id"])
        except (TypeError, ValueError):
            continue
        data[player_id] = row
    return data


def _normalize(value: float, *, lower: float, upper: float) -> float:
    if upper == lower:
        return lower
    clamped = max(lower, min(value, upper))
    return (clamped - lower) / (upper - lower) * 100.0


def _blend_rating(
    madden_ovr: float,
    pff_grade: Optional[float],
    pos: str,
) -> float:
    if pff_grade is None:
        return madden_ovr

    offense = pos in OFFENSE_POSITIONS
    defense = pos in DEFENSE_POSITIONS
    if pos == "QB":
        weight = 0.65
    elif offense:
        weight = 0.55
    elif pos in {"CB", "S"}:
        weight = 0.5
    elif defense:
        weight = 0.45
    else:
        weight = 0.5
    return madden_ovr * (1 - weight) + pff_grade * weight


def load_player_ratings(
    data_dir: Path,
    *,
    madden_filename: str = "madden25_sample.csv",
    pff_filename: str = "pff_sample.csv",
    season: Optional[int] = 2024,
) -> List[PlayerRating]:
    """Blend Madden and PFF data into unified player ratings."""

    madden = load_madden25(data_dir / madden_filename)
    pff = load_pff_grades(data_dir / pff_filename, season=season)

    players: List[PlayerRating] = []
    for player_id, row in madden.items():
        pos = row.get("pos", "").upper()
        madden_ovr = float(row.get("ovr", 0))
        pff_row = pff.get(player_id)
        pff_grade: Optional[float]
        if pff_row is None:
            pff_grade = None
        else:
            if pos in OFFENSE_POSITIONS:
                raw = pff_row.get("offense_grade")
            elif pos in {"CB", "S"}:
                raw = pff_row.get("coverage_grade") or pff_row.get("defense_grade")
            else:
                raw = pff_row.get("defense_grade") or pff_row.get("offense_grade")
            pff_grade = float(raw) if raw not in (None, "") else None

        blended = _blend_rating(madden_ovr, pff_grade, pos)
        overall = _normalize(blended, lower=40, upper=99)
        traits = {
            "speed": float(row.get("speed", 0)),
            "acceleration": float(row.get("acceleration", 0)),
            "strength": float(row.get("strength", 0)),
            "awareness": float(row.get("awareness", 0)),
        }
        players.append(
            PlayerRating(
                player_id=player_id,
                name=row.get("name", "Unknown"),
                pos=pos or "ATH",
                team_abbr=row.get("team_abbr", "FA"),
                overall=overall,
                madden_ovr=madden_ovr,
                pff_grade=pff_grade,
                traits=traits,
            )
        )
    return players
