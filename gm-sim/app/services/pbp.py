"""Utilities for importing nflfastR-style play-by-play data.

The real nflfastR dataset is sizeable, so this module focuses on the
aggregation logic needed by the simulator.  Callers provide rows that
mirror a subset of the public columns (team, player identifiers, EPA,
yards gained, etc.) and the helpers return blended ratings scaled to a
0-100 range for each positional group.

The same helpers back the `scripts/import_pbp.py` entry point which can
persist the aggregated data to JSON for downstream consumption.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping


@dataclass
class RatingEntry:
    """Normalized feature bundle for a single player."""

    player_id: str
    player_name: str
    team: str
    attempts: int
    secondary: int
    yards: float
    epa: float
    efficiency_primary: float
    efficiency_secondary: float
    rating: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "player_id": self.player_id,
            "player_name": self.player_name,
            "team": self.team,
            "attempts": self.attempts,
            "secondary": self.secondary,
            "yards": round(self.yards, 3),
            "epa": round(self.epa, 3),
            "efficiency_primary": round(self.efficiency_primary, 4),
            "efficiency_secondary": round(self.efficiency_secondary, 4),
            "rating": round(self.rating, 2),
        }


@dataclass
class RatingsOutput:
    """Container returned by :func:`derive_ratings`."""

    quarterbacks: List[RatingEntry]
    rushers: List[RatingEntry]
    receivers: List[RatingEntry]
    summary: Dict[str, Dict[str, float]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quarterbacks": [entry.to_dict() for entry in self.quarterbacks],
            "rushers": [entry.to_dict() for entry in self.rushers],
            "receivers": [entry.to_dict() for entry in self.receivers],
            "summary": self.summary,
        }


def load_rows(path: Path | str) -> List[Dict[str, str]]:
    """Load play-by-play rows from a CSV or JSON file."""

    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(source)

    if source.suffix.lower() == ".json":
        with source.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, list):
            raise ValueError("Expected a JSON array of play rows")
        return [dict(row) for row in data]

    if source.suffix.lower() != ".csv":
        raise ValueError("Only CSV or JSON sources are supported")

    with source.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _player_identifier(row: Mapping[str, Any], prefix: str) -> tuple[str, str]:
    player_id = (row.get(f"{prefix}_player_id") or "").strip()
    player_name = (row.get(f"{prefix}_player_name") or "").strip() or "Unknown"
    if not player_id:
        player_id = f"{prefix}:{player_name}"
    return player_id, player_name


def _team_for_row(row: Mapping[str, Any]) -> str:
    return (row.get("posteam") or row.get("pos_team") or "").strip()


def _parse_float(value: Any) -> float:
    if value in (None, "", "NA", "NaN"):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0


def _min_max_scale(values: Mapping[str, float]) -> Dict[str, float]:
    if not values:
        return {}
    min_val = min(values.values())
    max_val = max(values.values())
    if math.isclose(min_val, max_val, rel_tol=1e-9, abs_tol=1e-9):
        return {key: 50.0 for key in values}
    span = max_val - min_val
    return {key: ((val - min_val) / span) * 100.0 for key, val in values.items()}


def _build_summary(entries: Iterable[RatingEntry]) -> Dict[str, float]:
    ratings = [entry.rating for entry in entries]
    if not ratings:
        return {"count": 0, "mean": 0.0, "stdev": 0.0, "min": 0.0, "max": 0.0}
    if len(ratings) == 1:
        stdev_value = 0.0
    else:
        stdev_value = pstdev(ratings)
    return {
        "count": float(len(ratings)),
        "mean": round(mean(ratings), 3),
        "stdev": round(stdev_value, 3),
        "min": round(min(ratings), 2),
        "max": round(max(ratings), 2),
    }


def _finalize_entries(
    raw_entries: MutableMapping[str, Dict[str, Any]],
    primary_key: str,
    secondary_key: str,
    *,
    primary_weight: float,
    secondary_weight: float,
) -> List[RatingEntry]:
    if not raw_entries:
        return []

    primary_metrics: Dict[str, float] = {}
    secondary_metrics: Dict[str, float] = {}

    for key, payload in raw_entries.items():
        attempts = payload.get("attempts", 0)
        secondary = payload.get("secondary", 0)
        if attempts:
            payload[primary_key] = payload.get(primary_key, 0.0)
        else:
            payload[primary_key] = 0.0
        if secondary:
            payload[secondary_key] = payload.get(secondary_key, 0.0)
        else:
            payload[secondary_key] = 0.0
        primary_metrics[key] = payload[primary_key]
        secondary_metrics[key] = payload[secondary_key]

    primary_scaled = _min_max_scale(primary_metrics)
    secondary_scaled = _min_max_scale(secondary_metrics)

    entries: List[RatingEntry] = []
    for key, payload in raw_entries.items():
        rating = primary_weight * primary_scaled.get(
            key, 50.0
        ) + secondary_weight * secondary_scaled.get(key, 50.0)
        entries.append(
            RatingEntry(
                player_id=payload["player_id"],
                player_name=payload["player_name"],
                team=payload["team"],
                attempts=int(payload.get("attempts", 0)),
                secondary=int(payload.get("secondary", 0)),
                yards=float(payload.get("yards", 0.0)),
                epa=float(payload.get("epa", 0.0)),
                efficiency_primary=float(payload.get(primary_key, 0.0)),
                efficiency_secondary=float(payload.get(secondary_key, 0.0)),
                rating=rating,
            )
        )
    entries.sort(key=lambda entry: entry.rating, reverse=True)
    return entries


def derive_ratings(rows: Iterable[Mapping[str, Any]]) -> RatingsOutput:
    """Aggregate ratings for quarterbacks, rushers, and receivers."""

    qb_raw: Dict[str, Dict[str, Any]] = {}
    rb_raw: Dict[str, Dict[str, Any]] = {}
    wr_raw: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        epa = _parse_float(row.get("epa"))
        yards = _parse_float(row.get("yards_gained"))
        team = _team_for_row(row)

        passer_name = row.get("passer_player_name")
        if passer_name:
            passer_id, player_name = _player_identifier(row, "passer")
            entry = qb_raw.setdefault(
                passer_id,
                {
                    "player_id": passer_id,
                    "player_name": player_name,
                    "team": team,
                    "attempts": 0,
                    "secondary": 0,
                    "yards": 0.0,
                    "epa": 0.0,
                },
            )
            entry["attempts"] += 1
            entry["yards"] += yards
            entry["epa"] += epa
            entry.setdefault("completions", 0)
            entry["completions"] += _parse_int(row.get("complete_pass"))
            entry["secondary"] = entry["completions"]
            if entry["attempts"]:
                entry["epa_per_play"] = entry["epa"] / entry["attempts"]
                entry["completion_pct"] = entry["completions"] / entry["attempts"]
            else:
                entry["epa_per_play"] = 0.0
                entry["completion_pct"] = 0.0

        rusher_name = row.get("rusher_player_name")
        if rusher_name:
            rusher_id, player_name = _player_identifier(row, "rusher")
            entry = rb_raw.setdefault(
                rusher_id,
                {
                    "player_id": rusher_id,
                    "player_name": player_name,
                    "team": team,
                    "attempts": 0,
                    "secondary": 0,
                    "yards": 0.0,
                    "epa": 0.0,
                    "successes": 0,
                },
            )
            entry["attempts"] += 1
            entry["yards"] += yards
            entry["epa"] += epa
            if epa > 0:
                entry["successes"] += 1
            entry["secondary"] = entry["successes"]
            if entry["attempts"]:
                entry["success_rate"] = entry["successes"] / entry["attempts"]
                entry["yards_per_attempt"] = entry["yards"] / entry["attempts"]
            else:
                entry["success_rate"] = 0.0
                entry["yards_per_attempt"] = 0.0

        receiver_name = row.get("receiver_player_name")
        if receiver_name:
            receiver_id, player_name = _player_identifier(row, "receiver")
            entry = wr_raw.setdefault(
                receiver_id,
                {
                    "player_id": receiver_id,
                    "player_name": player_name,
                    "team": team,
                    "attempts": 0,
                    "secondary": 0,
                    "yards": 0.0,
                    "epa": 0.0,
                    "catches": 0,
                },
            )
            entry["attempts"] += 1
            entry["yards"] += yards
            entry["epa"] += epa
            entry["catches"] += _parse_int(row.get("complete_pass"))
            entry["secondary"] = entry["catches"]
            if entry["attempts"]:
                entry["catch_rate"] = entry["catches"] / entry["attempts"]
                entry["yards_per_target"] = entry["yards"] / entry["attempts"]
            else:
                entry["catch_rate"] = 0.0
                entry["yards_per_target"] = 0.0

    qb_entries = _finalize_entries(
        qb_raw,
        primary_key="epa_per_play",
        secondary_key="completion_pct",
        primary_weight=0.6,
        secondary_weight=0.4,
    )

    rb_entries = _finalize_entries(
        rb_raw,
        primary_key="yards_per_attempt",
        secondary_key="success_rate",
        primary_weight=0.5,
        secondary_weight=0.5,
    )

    wr_entries = _finalize_entries(
        wr_raw,
        primary_key="yards_per_target",
        secondary_key="catch_rate",
        primary_weight=0.55,
        secondary_weight=0.45,
    )

    summary = {
        "quarterbacks": _build_summary(qb_entries),
        "rushers": _build_summary(rb_entries),
        "receivers": _build_summary(wr_entries),
    }

    return RatingsOutput(qb_entries, rb_entries, wr_entries, summary)


def write_output(
    rows: Iterable[Mapping[str, Any]], destination: Path | str
) -> RatingsOutput:
    """Derive ratings and persist them to ``destination``.

    The destination directory will contain ``quarterbacks.json``,
    ``rushers.json``, ``receivers.json`` and ``summary.json`` files.
    """

    destination_path = Path(destination)
    destination_path.mkdir(parents=True, exist_ok=True)

    output = derive_ratings(rows)
    for key, entries in (
        ("quarterbacks", output.quarterbacks),
        ("rushers", output.rushers),
        ("receivers", output.receivers),
    ):
        with (destination_path / f"{key}.json").open("w", encoding="utf-8") as handle:
            json.dump([entry.to_dict() for entry in entries], handle, indent=2)

    with (destination_path / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(output.summary, handle, indent=2)

    return output


__all__ = [
    "RatingEntry",
    "RatingsOutput",
    "derive_ratings",
    "load_rows",
    "write_output",
]
