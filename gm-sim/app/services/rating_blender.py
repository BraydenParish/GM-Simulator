"""Utilities for blending multiple rating sources into a single score."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
import importlib

from typing import Any, Dict, Iterable, Mapping, Optional, List, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.pbp import RatingEntry, RatingsOutput


@dataclass(frozen=True)
class RatingSourceWeights:
    """Relative weighting for each rating source."""

    madden: float = 0.5
    pff: float = 0.3
    pbp: float = 0.2

    @property
    def total(self) -> float:
        return self.madden + self.pff + self.pbp


@dataclass
class BlendedRating:
    """Blended rating for a single player."""

    player_id: str
    rating: float
    confidence: float
    values: Dict[str, float]
    weight_share: Dict[str, float]

    def to_dict(self) -> Dict[str, object]:
        return {
            "player_id": self.player_id,
            "rating": round(self.rating, 2),
            "confidence": round(self.confidence, 3),
            "values": {key: round(value, 2) for key, value in self.values.items()},
            "weight_share": {
                key: round(value, 3) for key, value in self.weight_share.items()
            },
        }


def _clamp_rating(value: float) -> float:
    return max(0.0, min(100.0, value))


def _coerce_float(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _coerce_int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0


def _load_csv(path: Path | str, id_field: str, value_field: str) -> Dict[str, float]:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(source)
    ratings: Dict[str, float] = {}
    with source.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            player_id = (row.get(id_field) or "").strip()
            if not player_id:
                continue
            try:
                value = float(row.get(value_field, 0) or 0)
            except (TypeError, ValueError):
                continue
            ratings[player_id] = _clamp_rating(value)
    return ratings


def load_madden_ratings(
    path: Path | str, *, id_field: str = "player_id", value_field: str = "ovr"
) -> Dict[str, float]:
    """Load Madden-style overall ratings from a CSV file."""

    return _load_csv(path, id_field=id_field, value_field=value_field)


def load_pff_grades(
    path: Path | str, *, id_field: str = "player_id", value_field: str = "grade"
) -> Dict[str, float]:
    """Load PFF grades from a CSV file."""

    return _load_csv(path, id_field=id_field, value_field=value_field)


def load_blended_payload(path: Path | str) -> Dict[str, BlendedRating]:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(source)
    with source.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError("Expected a list of rating objects")
    results: Dict[str, BlendedRating] = {}
    for entry in payload:
        player_id = str(entry.get("player_id"))
        values = {str(k): float(v) for k, v in entry.get("values", {}).items()}
        weight_share = {
            str(k): float(v) for k, v in entry.get("weight_share", {}).items()
        }
        results[player_id] = BlendedRating(
            player_id=player_id,
            rating=float(entry.get("rating", 0.0)),
            confidence=float(entry.get("confidence", 0.0)),
            values=values,
            weight_share=weight_share,
        )
    return results


def pbp_ratings_map(
    output: RatingsOutput | Mapping[str, Iterable[Mapping[str, object]]],
) -> Dict[str, float]:
    """Return a simple mapping of player id to rating from play-by-play data."""

    def _extract(
        entries: Iterable[RatingEntry | Mapping[str, object]],
    ) -> Iterable[RatingEntry]:
        for item in entries:
            if isinstance(item, RatingEntry):
                yield item
            else:
                yield RatingEntry(
                    player_id=str(item.get("player_id", "")),
                    player_name=str(item.get("player_name", "")),
                    team=str(item.get("team", "")),
                    attempts=_coerce_int(item.get("attempts", 0)),
                    secondary=_coerce_int(item.get("secondary", 0)),
                    yards=_coerce_float(item.get("yards", 0.0)),
                    epa=_coerce_float(item.get("epa", 0.0)),
                    efficiency_primary=_coerce_float(
                        item.get("efficiency_primary", 0.0)
                    ),
                    efficiency_secondary=_coerce_float(
                        item.get("efficiency_secondary", 0.0)
                    ),
                    rating=_coerce_float(item.get("rating", 0.0)),
                )

    ratings: Dict[str, float] = {}
    if isinstance(output, RatingsOutput):
        iterables: List[Iterable[RatingEntry]] = [
            output.quarterbacks,
            output.rushers,
            output.receivers,
        ]
    else:
        iterables = [
            _extract(output.get("quarterbacks", [])),
            _extract(output.get("rushers", [])),
            _extract(output.get("receivers", [])),
        ]
    for group in iterables:
        for entry in _extract(group):
            if entry.player_id:
                ratings[entry.player_id] = _clamp_rating(entry.rating)
    return ratings


def blend_ratings(
    madden: Mapping[str, float],
    pff: Mapping[str, float],
    pbp: Mapping[str, float],
    *,
    weights: RatingSourceWeights = RatingSourceWeights(),
    fallback: float = 50.0,
) -> Dict[str, BlendedRating]:
    """Blend ratings from multiple sources using the supplied weights."""

    blended: Dict[str, BlendedRating] = {}
    total_weight = max(weights.total, 1e-6)
    all_keys = set(madden) | set(pff) | set(pbp)
    for player_id in sorted(all_keys):
        source_values: Dict[str, float] = {}
        weighted_sum = 0.0
        weight_accumulator = 0.0
        weight_share: Dict[str, float] = {}
        for source_name, source_map, source_weight in (
            ("madden", madden, weights.madden),
            ("pff", pff, weights.pff),
            ("pbp", pbp, weights.pbp),
        ):
            value = source_map.get(player_id)
            if value is None:
                continue
            clamped_value = _clamp_rating(value)
            source_values[source_name] = clamped_value
            weighted_sum += clamped_value * source_weight
            weight_accumulator += source_weight
        if weight_accumulator:
            rating = weighted_sum / weight_accumulator
            for source_name in source_values:
                source_weight = getattr(weights, source_name, 0.0)
                if source_weight:
                    weight_share[source_name] = source_weight / weight_accumulator
        else:
            rating = fallback
        confidence = weight_accumulator / total_weight if total_weight else 0.0
        blended[player_id] = BlendedRating(
            player_id=player_id,
            rating=rating,
            confidence=confidence,
            values=source_values,
            weight_share=weight_share,
        )
    return blended


def write_blended_output(
    blended: Mapping[str, BlendedRating], path: Path | str
) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [blended[player_id].to_dict() for player_id in sorted(blended)]
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


async def apply_blended_ratings(
    session: AsyncSession,
    blended: Mapping[str, BlendedRating],
    *,
    fallback_identifier: str = "name",
) -> None:
    """Persist blended ratings onto player records."""

    if not blended:
        return
    models = importlib.import_module("app.models")
    player_model = getattr(models, "Player")

    players = (await session.execute(select(player_model))).scalars().all()
    for raw_player in players:
        player = cast(Any, raw_player)
        identifiers = {str(player.id)}
        if fallback_identifier == "name" and player.name:
            identifiers.add(player.name.lower())
        match: Optional[BlendedRating] = None
        for identifier in identifiers:
            match = blended.get(identifier)
            if match:
                break
        if not match:
            continue
        player.blended_rating = match.rating
        player.rating_confidence = match.confidence
        player.rating_components = {
            source: {
                "value": value,
                "weight": match.weight_share.get(source, 0.0),
            }
            for source, value in match.values.items()
        }
        player.pbp_rating = match.values.get("pbp")
        player.madden_rating = match.values.get("madden")
        player.pff_grade = match.values.get("pff")
    await session.flush()
