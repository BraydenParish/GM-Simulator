"""Coaching system helpers that tie scheme fits into gameplay outcomes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Coach, CoachAssignment, Team


@dataclass
class CoachProfile:
    """Lightweight view of a coach used for scoring."""

    id: int
    name: str
    role: str
    scheme: str
    leadership: float
    development: float
    tactics: float
    discipline: float
    experience_years: int


@dataclass
class TeamCoachEffect:
    """Aggregate modifiers computed from a team's active staff."""

    team_id: int
    offense_scheme: Optional[str] = None
    defense_scheme: Optional[str] = None
    rating_bonus: float = 0.0
    offense_bonus: float = 0.0
    defense_bonus: float = 0.0
    development_bonus: float = 0.0
    cap_efficiency: float = 0.0
    scheme_alignment: float = 0.0
    notes: List[str] = field(default_factory=list)

    def register_assignment(self, assignment_role: str, coach: CoachProfile) -> None:
        role = assignment_role.upper()
        leadership_weight = 0.75 if role == "HC" else 0.35
        tactics_weight = 0.45 if role == "HC" else 0.55
        development_weight = 0.50 if role == "HC" else 0.30
        rating_gain = coach.leadership * leadership_weight
        tactical_gain = coach.tactics * tactics_weight
        self.rating_bonus += round(rating_gain, 2)
        if role in {"HC", "OC"}:
            alignment = self._scheme_alignment(coach.scheme, self.offense_scheme)
            self.offense_bonus += round(tactical_gain + alignment, 2)
            if alignment:
                self.notes.append(
                    f"{coach.name}'s {coach.scheme} offense fits perfectly ( +{alignment:.1f} )"
                )
        if role in {"HC", "DC"}:
            alignment = self._scheme_alignment(coach.scheme, self.defense_scheme)
            self.defense_bonus += round(tactical_gain + alignment, 2)
            if alignment:
                self.notes.append(
                    f"{coach.name}'s {coach.scheme} defense fits perfectly ( +{alignment:.1f} )"
                )
        if role not in {"OC", "DC", "HC"}:
            self.rating_bonus += round(coach.tactics * 0.25, 2)
        self.development_bonus += round(coach.development * development_weight, 2)
        self.cap_efficiency += round(coach.discipline * 0.05, 3)
        self.scheme_alignment += self._scheme_alignment_score(coach.scheme)
        if coach.experience_years:
            veteran_note = f"{coach.name} adds playoff poise from {coach.experience_years} seasons"
            self.notes.append(veteran_note)

    @staticmethod
    def _scheme_alignment(coach_scheme: Optional[str], team_scheme: Optional[str]) -> float:
        if not coach_scheme or not team_scheme:
            return 0.0
        if coach_scheme.lower() == team_scheme.lower():
            return 2.5
        if coach_scheme.split()[0].lower() == team_scheme.split()[0].lower():
            return 1.0
        return 0.0

    def _scheme_alignment_score(self, coach_scheme: Optional[str]) -> float:
        if not coach_scheme:
            return 0.0
        alignment = 0.0
        if self.offense_scheme and coach_scheme.lower() in self.offense_scheme.lower():
            alignment += 0.5
        if self.defense_scheme and coach_scheme.lower() in self.defense_scheme.lower():
            alignment += 0.5
        return alignment

    def apply_to_rating(self, base_rating: float) -> float:
        adjusted = base_rating + self.rating_adjustment()
        return max(1.0, round(adjusted, 2))

    def rating_adjustment(self) -> float:
        return round(self.rating_bonus + self.offense_bonus + self.defense_bonus, 2)

    def development_rate_bonus(self) -> float:
        return round(self.development_bonus * 0.01, 3)

    def to_dict(self) -> Dict[str, object]:
        return {
            "rating_adjustment": self.rating_adjustment(),
            "development_rate_bonus": self.development_rate_bonus(),
            "cap_efficiency": round(self.cap_efficiency, 3),
            "scheme_alignment": round(self.scheme_alignment, 2),
            "notes": list(self.notes),
        }


class CoachingSystem:
    """Loads coaching data and exposes matchup-aware modifiers."""

    def __init__(self, team_effects: Dict[int, TeamCoachEffect]):
        self._effects = team_effects

    @classmethod
    async def build(cls, session: AsyncSession) -> "CoachingSystem":
        query: Select = (
            select(CoachAssignment, Coach, Team)
            .join(Coach, CoachAssignment.coach_id == Coach.id)
            .join(Team, CoachAssignment.team_id == Team.id)
            .where(CoachAssignment.active.is_(True))
        )
        result = await session.execute(query)
        effects: Dict[int, TeamCoachEffect] = {}
        for assignment, coach, team in result.all():
            effect = effects.setdefault(
                team.id,
                TeamCoachEffect(
                    team_id=team.id,
                    offense_scheme=team.scheme_off,
                    defense_scheme=team.scheme_def,
                ),
            )
            profile = CoachProfile(
                id=coach.id,
                name=coach.name,
                role=assignment.role,
                scheme=coach.scheme,
                leadership=coach.leadership,
                development=coach.development,
                tactics=coach.tactics,
                discipline=coach.discipline,
                experience_years=coach.experience_years,
            )
            effect.register_assignment(assignment.role, profile)
        return cls(effects)

    def effect_for(self, team_id: int) -> TeamCoachEffect:
        return self._effects.get(
            team_id,
            TeamCoachEffect(team_id=team_id),
        )

    def describe_matchup(self, home_team: int, away_team: int) -> Dict[str, Dict[str, object]]:
        return {
            "home": self.effect_for(home_team).to_dict(),
            "away": self.effect_for(away_team).to_dict(),
        }

    def ranked_staff(self) -> List[tuple[int, float]]:
        return sorted(
            ((team_id, effect.rating_adjustment()) for team_id, effect in self._effects.items()),
            key=lambda item: item[1],
            reverse=True,
        )

    def apply_rating(self, team_id: int, base_rating: float) -> float:
        effect = self.effect_for(team_id)
        return effect.apply_to_rating(base_rating)

    def development_bonus(self, team_id: int) -> float:
        return self.effect_for(team_id).development_rate_bonus()
