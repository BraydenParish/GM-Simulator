"""Injury and fatigue modelling utilities."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional

DEFAULT_POSITION_RATES: Dict[str, float] = {
    "QB": 0.00045,
    "RB": 0.00095,
    "WR": 0.0008,
    "TE": 0.00075,
    "OL": 0.0006,
    "DL": 0.00075,
    "EDGE": 0.00085,
    "LB": 0.0009,
    "CB": 0.0009,
    "S": 0.00085,
    "K": 0.0002,
    "P": 0.0002,
    "LS": 0.0001,
    "DEFAULT": 0.00075,
}

SEVERITY_BUCKETS: Dict[str, Dict[str, object]] = {
    "minor": {"prob": 0.68, "weeks": (1, 1)},
    "moderate": {"prob": 0.2, "weeks": (2, 4)},
    "major": {"prob": 0.1, "weeks": (5, 8)},
    "season": {"prob": 0.02, "weeks": (9, 17)},
}

INJURY_TYPES: Dict[str, List[str]] = {
    "QB": ["Shoulder sprain", "Ankle tweak", "Rib bruise"],
    "RB": ["Hamstring pull", "High-ankle sprain", "Knee sprain"],
    "WR": ["Hamstring pull", "Groin strain", "Foot sprain"],
    "TE": ["Knee sprain", "Back spasms", "Shoulder sprain"],
    "OL": ["Knee sprain", "Shoulder strain", "Back tightness"],
    "DL": ["Calf strain", "Shoulder sprain", "Knee contusion"],
    "EDGE": ["Ankle sprain", "Groin strain", "Shoulder sprain"],
    "LB": ["Shoulder sprain", "Knee sprain", "Ankle sprain"],
    "CB": ["Hamstring pull", "Calf strain", "Knee sprain"],
    "S": ["Shoulder sprain", "Hamstring pull", "Groin strain"],
    "K": ["Hip flexor strain", "Quad strain"],
    "P": ["Hip flexor strain", "Back tightness"],
    "LS": ["Shoulder sprain"],
}

FATIGUE_PER_SNAP = 0.32
FATIGUE_RECOVERY = 18.0
MAX_FATIGUE = 100.0
FATIGUE_THRESHOLD = 60.0
MIN_SNAP_SHARE = 0.35


@dataclass
class PlayerParticipation:
    """Tracks expected snaps and health for a player in the sim."""

    player_id: int
    position: str
    snaps: int
    fatigue: float = 0.0
    injury_weeks_remaining: int = 0
    player_name: str = ""

    def active_snaps(self) -> int:
        """Returns the effective snaps given current fatigue/injury state."""

        if self.injury_weeks_remaining > 0 or self.snaps <= 0:
            return 0
        if self.fatigue <= FATIGUE_THRESHOLD:
            return self.snaps
        fatigue_penalty = min(self.fatigue - FATIGUE_THRESHOLD, MAX_FATIGUE)
        multiplier = max(MIN_SNAP_SHARE, 1.0 - fatigue_penalty / (MAX_FATIGUE + 1.0))
        return int(self.snaps * multiplier)


@dataclass
class InjuryEvent:
    """Represents an injury incurred during a simulated game."""

    player_id: int
    team_id: int
    severity: str
    weeks_out: int
    occurred_snap: int
    injury_type: str
    week: int | None = None
    season: int | None = None

    def to_dict(
        self,
        *,
        current_week: int | None = None,
        season: int | None = None,
    ) -> Dict[str, int | str | None]:
        """Serialize the injury for persistence and APIs."""

        week_value = current_week if current_week is not None else self.week
        season_value = season if season is not None else self.season
        expected_return: int | None = None
        if week_value is not None:
            expected_return = week_value + max(int(self.weeks_out), 0)
        return {
            "player_id": self.player_id,
            "team_id": self.team_id,
            "severity": self.severity,
            "weeks_out": int(self.weeks_out),
            "occurred_snap": int(self.occurred_snap),
            "injury_type": self.injury_type,
            "week": week_value,
            "season": season_value,
            "expected_return_week": expected_return,
        }


class InjuryEngine:
    """Probabilistic injury generator with fatigue accumulation."""

    def __init__(
        self,
        *,
        rng: Optional[random.Random] = None,
        position_rates: Optional[Mapping[str, float]] = None,
        severity_buckets: Optional[Mapping[str, Mapping[str, object]]] = None,
        fatigue_per_snap: float = FATIGUE_PER_SNAP,
        fatigue_recovery: float = FATIGUE_RECOVERY,
    ) -> None:
        self._rng = rng or random.Random()
        self._position_rates = dict(position_rates or DEFAULT_POSITION_RATES)
        self._severity_buckets = dict(severity_buckets or SEVERITY_BUCKETS)
        self._fatigue_per_snap = fatigue_per_snap
        self._fatigue_recovery = fatigue_recovery

    def simulate_game(
        self,
        team_id: int,
        participants: Iterable[PlayerParticipation],
    ) -> List[InjuryEvent]:
        events: List[InjuryEvent] = []
        for participant in participants:
            active_snaps = participant.active_snaps()
            if active_snaps <= 0:
                continue
            per_snap_rate = self._rate_for_position(participant.position)
            fatigue_multiplier = 1.0 + max(participant.fatigue, 0.0) / 100.0
            per_snap_rate *= fatigue_multiplier
            per_snap_rate = min(per_snap_rate, 0.25)
            probability = 1.0 - (1.0 - per_snap_rate) ** active_snaps
            if self._rng.random() < probability:
                severity = self._choose_severity()
                weeks_out = self._roll_weeks(severity)
                injury_type = self._pick_injury_type(participant.position)
                occurred_snap = self._rng.randint(1, active_snaps)
                participant.injury_weeks_remaining = weeks_out
                events.append(
                    InjuryEvent(
                        player_id=participant.player_id,
                        team_id=team_id,
                        severity=severity,
                        weeks_out=weeks_out,
                        occurred_snap=occurred_snap,
                        injury_type=injury_type,
                    )
                )
            participant.fatigue = min(
                MAX_FATIGUE,
                participant.fatigue + active_snaps * self._fatigue_per_snap,
            )
        return events

    def rest_week(self, rosters: Mapping[int, List[PlayerParticipation]]) -> None:
        """Advances the calendar by one week for fatigue/injury recovery."""

        for roster in rosters.values():
            for participant in roster:
                if participant.injury_weeks_remaining > 0:
                    participant.injury_weeks_remaining = max(
                        0, participant.injury_weeks_remaining - 1
                    )
                if participant.fatigue > 0:
                    participant.fatigue = max(0.0, participant.fatigue - self._fatigue_recovery)

    def team_availability_penalty(self, roster: Iterable[PlayerParticipation]) -> float:
        """Returns a rating penalty driven by fatigue and unavailable starters."""

        injury_penalty = 0.0
        fatigue_penalty = 0.0
        for participant in roster:
            if participant.injury_weeks_remaining > 0:
                injury_penalty += 4.0
            else:
                fatigue_penalty += max(0.0, participant.fatigue - FATIGUE_THRESHOLD) / 10.0
        return injury_penalty + fatigue_penalty

    def _rate_for_position(self, position: str) -> float:
        return self._position_rates.get(position.upper(), self._position_rates["DEFAULT"])

    def _choose_severity(self) -> str:
        roll = self._rng.random()
        cumulative = 0.0
        fallback = "minor"
        for severity, config in self._severity_buckets.items():
            prob = float(config.get("prob", 0.0))
            cumulative += prob
            if roll <= cumulative:
                return severity
            fallback = severity
        return fallback

    def _roll_weeks(self, severity: str) -> int:
        config = self._severity_buckets.get(severity)
        if not config:
            return 1
        low, high = config.get("weeks", (1, 1))  # type: ignore[assignment]
        return self._rng.randint(int(low), int(high))

    def _pick_injury_type(self, position: str) -> str:
        candidates = INJURY_TYPES.get(position.upper())
        if not candidates:
            candidates = ["Soft-tissue strain"]
        return self._rng.choice(candidates)
