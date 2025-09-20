"""Utilities for generating rookie draft classes."""

from __future__ import annotations

import random
from typing import Dict, List, Sequence, Set, Tuple

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Player
from app.schemas import DraftClassGenerationRequest

DEFAULT_POSITION_WEIGHTS: Dict[str, float] = {
    "QB": 4.0,
    "RB": 9.0,
    "WR": 14.0,
    "TE": 6.0,
    "OT": 6.0,
    "OG": 6.0,
    "C": 3.0,
    "DT": 8.0,
    "EDGE": 8.0,
    "LB": 8.0,
    "CB": 10.0,
    "S": 5.0,
    "K": 2.0,
    "P": 2.0,
}

FIRST_NAMES: Sequence[str] = (
    "Jalen",
    "Caleb",
    "Drake",
    "Jordan",
    "Xavier",
    "Zion",
    "Micah",
    "Noah",
    "Ezekiel",
    "Aiden",
    "Trevon",
    "Isaiah",
    "Cole",
    "Darius",
    "Julian",
    "Roman",
    "Kai",
    "Logan",
    "Tyson",
    "Preston",
)

LAST_NAMES: Sequence[str] = (
    "Harrison",
    "Mitchell",
    "Douglas",
    "Saunders",
    "Ramirez",
    "Jefferson",
    "Bennett",
    "Hayes",
    "Livingston",
    "Carson",
    "Whitaker",
    "Matthews",
    "Baldwin",
    "Fowler",
    "Vaughn",
    "Franklin",
    "Goodwin",
    "Hendricks",
    "Irvin",
    "Jacobs",
)

POSITION_PHYSICAL_RANGES: Dict[str, Tuple[Tuple[int, int], Tuple[int, int]]] = {
    "QB": ((73, 78), (210, 240)),
    "RB": ((68, 73), (200, 225)),
    "WR": ((71, 76), (190, 215)),
    "TE": ((75, 79), (240, 265)),
    "OT": ((77, 81), (300, 325)),
    "OG": ((75, 79), (305, 330)),
    "C": ((74, 78), (295, 320)),
    "DT": ((75, 78), (300, 330)),
    "EDGE": ((75, 78), (255, 275)),
    "LB": ((73, 76), (235, 255)),
    "CB": ((70, 73), (190, 205)),
    "S": ((72, 75), (200, 215)),
    "K": ((70, 74), (180, 200)),
    "P": ((72, 75), (190, 210)),
}

POSITION_ATTRIBUTE_RANGES: Dict[str, Dict[str, Tuple[int, int]]] = {
    "QB": {
        "spd": (72, 86),
        "acc": (80, 94),
        "agi": (76, 90),
        "str": (55, 70),
        "awr": (70, 90),
        "thp": (86, 97),
        "tha_s": (78, 95),
        "tha_m": (76, 94),
        "tha_d": (72, 93),
        "tup": (74, 92),
    },
    "RB": {
        "spd": (88, 97),
        "acc": (88, 97),
        "agi": (84, 95),
        "str": (66, 80),
        "awr": (60, 78),
        "cth": (62, 80),
        "cit": (60, 78),
    },
    "WR": {
        "spd": (90, 98),
        "acc": (90, 97),
        "agi": (88, 96),
        "str": (60, 75),
        "awr": (62, 82),
        "cth": (72, 92),
        "cit": (66, 90),
        "rr": (70, 92),
        "rel": (62, 80),
    },
    "TE": {
        "spd": (80, 90),
        "acc": (82, 92),
        "agi": (76, 88),
        "str": (72, 86),
        "awr": (65, 82),
        "cth": (70, 88),
        "cit": (68, 90),
        "pbk": (62, 78),
        "rbk": (62, 80),
    },
    "OT": {
        "spd": (62, 70),
        "acc": (68, 78),
        "agi": (60, 72),
        "str": (88, 96),
        "awr": (65, 84),
        "pbk": (76, 90),
        "rbk": (74, 88),
        "iblk": (78, 90),
        "obl": (70, 86),
    },
    "OG": {
        "spd": (58, 66),
        "acc": (64, 74),
        "agi": (56, 68),
        "str": (90, 96),
        "awr": (64, 82),
        "pbk": (74, 88),
        "rbk": (76, 90),
        "iblk": (80, 92),
        "obl": (70, 84),
    },
    "C": {
        "spd": (60, 70),
        "acc": (66, 76),
        "agi": (60, 74),
        "str": (88, 94),
        "awr": (70, 88),
        "pbk": (74, 88),
        "rbk": (74, 88),
        "iblk": (78, 90),
        "obl": (68, 82),
    },
    "DT": {
        "spd": (70, 80),
        "acc": (74, 86),
        "agi": (68, 80),
        "str": (90, 96),
        "awr": (64, 82),
        "pmv": (70, 88),
        "fmv": (68, 86),
        "bsh": (74, 90),
    },
    "EDGE": {
        "spd": (84, 94),
        "acc": (84, 95),
        "agi": (80, 92),
        "str": (78, 90),
        "awr": (64, 82),
        "pmv": (78, 92),
        "fmv": (76, 90),
        "bsh": (72, 88),
    },
    "LB": {
        "spd": (82, 92),
        "acc": (84, 94),
        "agi": (80, 90),
        "str": (80, 90),
        "awr": (68, 86),
        "purs": (78, 92),
        "mcv": (62, 76),
        "zcv": (70, 86),
    },
    "CB": {
        "spd": (92, 99),
        "acc": (92, 99),
        "agi": (90, 98),
        "str": (60, 72),
        "awr": (64, 84),
        "mcv": (78, 94),
        "zcv": (76, 92),
        "prs": (72, 90),
    },
    "S": {
        "spd": (88, 95),
        "acc": (88, 96),
        "agi": (84, 92),
        "str": (78, 88),
        "awr": (70, 88),
        "mcv": (68, 84),
        "zcv": (76, 90),
        "prs": (68, 86),
        "purs": (78, 92),
    },
    "K": {
        "spd": (60, 70),
        "acc": (68, 78),
        "agi": (62, 72),
        "str": (60, 70),
        "awr": (68, 86),
    },
    "P": {
        "spd": (60, 70),
        "acc": (66, 76),
        "agi": (60, 74),
        "str": (60, 72),
        "awr": (68, 86),
    },
}


async def _existing_names(db: AsyncSession) -> Set[str]:
    result = await db.execute(select(Player.name))
    return {row[0] for row in result if row[0]}


def _normalise_weights(weights: Dict[str, float]) -> List[Tuple[str, float]]:
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("position weights must sum to a positive value")
    cumulative: List[Tuple[str, float]] = []
    running = 0.0
    for pos, weight in weights.items():
        running += weight / total
        cumulative.append((pos, running))
    cumulative[-1] = (cumulative[-1][0], 1.0)
    return cumulative


def _choose_position(rng: random.Random, cumulative: List[Tuple[str, float]]) -> str:
    roll = rng.random()
    for pos, threshold in cumulative:
        if roll <= threshold:
            return pos
    return cumulative[-1][0]


def _generate_name(rng: random.Random, existing: Set[str]) -> str:
    for _ in range(256):
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        if name not in existing:
            existing.add(name)
            return name
    suffix = rng.randint(1, 9999)
    fallback = f"Prospect {suffix}"
    existing.add(fallback)
    return fallback


def _random_range(rng: random.Random, bounds: Tuple[int, int]) -> int:
    low, high = bounds
    if low >= high:
        return low
    return rng.randint(low, high)


def _generate_overall(
    rng: random.Random,
    base: float,
    stddev: float,
    pick_index: int,
    players_per_round: int,
) -> int:
    round_index = pick_index // players_per_round
    round_boost = max(0.0, 6.0 - 1.4 * round_index)
    raw = rng.gauss(base + round_boost, stddev)
    return max(45, min(88, int(round(raw))))


def _generate_potential(rng: random.Random, overall: int) -> int:
    bonus = rng.randint(4, 12)
    return max(overall, min(96, overall + bonus))


def _build_attributes(rng: random.Random, position: str) -> Dict[str, int]:
    template = POSITION_ATTRIBUTE_RANGES.get(position, {})
    return {attr: _random_range(rng, bounds) for attr, bounds in template.items()}


def _physical_profile(rng: random.Random, position: str) -> Tuple[int, int]:
    bounds = POSITION_PHYSICAL_RANGES.get(position)
    if bounds is None:
        return _random_range(rng, (72, 78)), _random_range(rng, (205, 235))
    (h_low, h_high), (w_low, w_high) = bounds
    return _random_range(rng, (h_low, h_high)), _random_range(rng, (w_low, w_high))


async def generate_draft_class(
    db: AsyncSession, request: DraftClassGenerationRequest
) -> List[Player]:
    """Create a rookie class for the supplied season."""

    year = request.year
    total_players = request.rounds * request.players_per_round
    if total_players <= 0:
        raise HTTPException(status_code=422, detail="draft class size must be positive")

    existing_rookies = await db.execute(select(Player.id).where(Player.rookie_year == year))
    if list(existing_rookies):
        raise HTTPException(status_code=409, detail="draft class already generated for this year")

    if request.position_weights:
        weights = {pos.upper(): weight for pos, weight in request.position_weights.items()}
    else:
        weights = DEFAULT_POSITION_WEIGHTS.copy()

    cumulative = _normalise_weights(weights)
    rng = random.Random(request.seed)
    names = await _existing_names(db)

    new_players: List[Player] = []
    for pick_index in range(total_players):
        position = _choose_position(rng, cumulative)
        overall = _generate_overall(
            rng,
            request.base_overall,
            request.overall_stddev,
            pick_index,
            request.players_per_round,
        )
        potential = _generate_potential(rng, overall)
        height, weight = _physical_profile(rng, position)
        age = rng.choice([21, 22, 23])
        stamina = rng.randint(72, 88)
        morale = rng.randint(48, 65)
        attrs = _build_attributes(rng, position)
        name = _generate_name(rng, names)
        player = Player(
            name=name,
            pos=position,
            team_id=None,
            rookie_year=year,
            age=age,
            height=height,
            weight=weight,
            ovr=overall,
            pot=potential,
            stamina=stamina,
            morale=morale,
            injury_status="OK",
            **attrs,
        )
        new_players.append(player)

    db.add_all(new_players)
    await db.flush()
    await db.commit()
    for player in new_players:
        await db.refresh(player)
    return new_players
