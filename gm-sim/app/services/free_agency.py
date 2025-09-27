from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Player, Team
from app.schemas import (
    FreeAgentBiddingRequest,
    FreeAgentBiddingResult,
    FreeAgentOfferEvaluation,
    FreeAgentProjectionRead,
    FreeAgentSigningPlan,
    FreeAgentSigningResponse,
    FreeAgentSummary,
)
from app.schemas import ContractRead, ContractSignRequest
from app.services.coaching import CoachingSystem
from app.services.contracts import sign_contract

_DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "free_agents.json"


@lru_cache(maxsize=1)
def _load_projection_table() -> dict[str, list[dict[str, str]]]:
    if not _DATA_PATH.exists():
        return {}
    with _DATA_PATH.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    normalized: dict[str, list[dict[str, str]]] = {}
    for season, entries in raw.items():
        normalized[str(season)] = [dict(entry) for entry in entries]
    return normalized


async def _resolve_player(
    db: AsyncSession, name: str
) -> tuple[Player | None, Team | None]:
    query: Select = (
        select(Player, Team)
        .outerjoin(Team, Player.team_id == Team.id)
        .where(Player.name.ilike(name))
    )
    result = await db.execute(query.limit(1))
    row = result.first()
    if not row:
        return None, None
    player, team = row
    return player, team


async def project_free_agents(
    db: AsyncSession,
    season: int,
    *,
    limit: Optional[int] = None,
) -> List[FreeAgentProjectionRead]:
    table = _load_projection_table()
    entries = table.get(str(season), [])
    projections: List[FreeAgentProjectionRead] = []
    for index, entry in enumerate(entries):
        if limit is not None and index >= limit:
            break
        player, team = await _resolve_player(db, entry.get("name", ""))
        projections.append(
            FreeAgentProjectionRead(
                season=season,
                name=entry.get("name", "Unknown"),
                pos=entry.get("pos"),
                tier=entry.get("tier"),
                expected_market=entry.get("expected_market"),
                notes=entry.get("notes"),
                source=entry.get("source"),
                player_id=player.id if player else None,
                overall=player.ovr if player else None,
                age=player.age if player else None,
                current_team_id=player.team_id if player else None,
                current_team_abbr=team.abbr if team else None,
            )
        )
    return projections


async def list_free_agents(
    db: AsyncSession,
    *,
    limit: Optional[int] = None,
) -> List[FreeAgentSummary]:
    query: Select = (
        select(Player)
        .where(Player.team_id.is_(None))
        .order_by(Player.ovr.desc().nullslast(), Player.age.asc().nullslast(), Player.name.asc())
    )
    if limit is not None:
        query = query.limit(limit)
    result = await db.execute(query)
    players = result.scalars().all()
    summaries: List[FreeAgentSummary] = []
    for player in players:
        summaries.append(
            FreeAgentSummary(
                player_id=player.id,
                name=player.name,
                pos=player.pos,
                age=player.age,
                overall=player.ovr,
                stamina=player.stamina,
            )
        )
    return summaries


def _build_salary_schedule(plan: FreeAgentSigningPlan) -> dict[int, int]:
    if plan.years <= 0:
        raise ValueError("Contract must be at least one year")
    base_cash = max(0, plan.total_value - plan.signing_bonus)
    per_year, remainder = divmod(base_cash, plan.years)
    schedule: dict[int, int] = {}
    for index in range(plan.years):
        year = plan.start_year + index
        schedule[year] = per_year + (1 if index < remainder else 0)
    return schedule


async def sign_free_agent(
    db: AsyncSession,
    plan: FreeAgentSigningPlan,
) -> FreeAgentSigningResponse:
    schedule = _build_salary_schedule(plan)
    end_year = plan.start_year + plan.years - 1
    guarantees = plan.guarantees_total
    if guarantees is None:
        first_year = schedule.get(plan.start_year, 0)
        guarantees = plan.signing_bonus + first_year
    contract_request = ContractSignRequest(
        player_id=plan.player_id,
        team_id=plan.team_id,
        start_year=plan.start_year,
        end_year=end_year,
        base_salary_yearly=schedule,
        signing_bonus_total=plan.signing_bonus,
        guarantees_total=guarantees,
        no_trade=plan.no_trade,
        void_years=plan.void_years,
    )
    contract = await sign_contract(db, contract_request)
    team = await db.get(Team, plan.team_id)
    return FreeAgentSigningResponse(
        contract=ContractRead.model_validate(contract),
        team_cap_space=team.cap_space if team else 0,
    )


async def evaluate_free_agent_bidding(
    db: AsyncSession,
    request: FreeAgentBiddingRequest,
    *,
    coaching: CoachingSystem | None = None,
) -> FreeAgentBiddingResult:
    player = await db.get(Player, request.player_id)
    if player is None:
        raise ValueError("Player not found for bidding evaluation")

    system = coaching or await CoachingSystem.build(db)
    evaluations: List[FreeAgentOfferEvaluation] = []

    for offer in request.offers:
        team = await db.get(Team, offer.team_id)
        if team is None:
            continue
        cap_space = team.cap_space
        base_apv = offer.total_value / max(offer.years, 1)
        signing_component = offer.signing_bonus * 0.08
        guarantee_component = (offer.guarantees_total or offer.signing_bonus) * 0.04
        contender_component = 0.0
        if request.prefer_contender and team.elo is not None:
            contender_component = max(0.0, (team.elo - 1500) / 75.0)
        coaching_effect = system.effect_for(team.id)
        development_component = coaching_effect.development_rate_bonus() * 120
        rating_component = coaching_effect.rating_adjustment() * 0.15
        loyalty_component = 0.0
        if player.team_id == team.id:
            loyalty_component = max(request.loyalty_weight, 0.0) * 5.0
        scheme_component = 0.0
        if offer.scheme_pitch:
            pitch_lower = offer.scheme_pitch.lower()
            offense = (team.scheme_off or "").lower()
            defense = (team.scheme_def or "").lower()
            if pitch_lower and (pitch_lower in offense or pitch_lower in defense):
                scheme_component = 2.5

        notes: List[str] = []
        if offer.pitch:
            notes.append(offer.pitch)
        if coaching_effect.notes:
            notes.extend(coaching_effect.notes[:2])
        if cap_space is not None and cap_space < offer.total_value / max(1, offer.years):
            notes.append("Cap squeeze warning")
        if scheme_component:
            notes.append("Scheme fit bonus applied")
        if contender_component:
            notes.append("Contender premium applied")

        score = (
            base_apv
            + signing_component
            + guarantee_component
            + contender_component
            + development_component
            + rating_component
            + loyalty_component
            + scheme_component
        )

        evaluations.append(
            FreeAgentOfferEvaluation(
                team_id=team.id,
                score=round(score, 2),
                years=offer.years,
                total_value=offer.total_value,
                signing_bonus=offer.signing_bonus,
                guarantees_total=offer.guarantees_total,
                cap_space=cap_space,
                notes=notes,
            )
        )

    if not evaluations:
        raise ValueError("No valid offers provided for bidding evaluation")

    ranked = sorted(evaluations, key=lambda entry: entry.score, reverse=True)
    winner = ranked[0]
    rationale_parts = [
        f"{winner.total_value // max(winner.years, 1)} AAV led the market",
        f"coaching boosted score by {system.effect_for(winner.team_id).rating_adjustment():.1f}",
    ]
    if winner.notes:
        rationale_parts.append("; ".join(winner.notes[:2]))

    return FreeAgentBiddingResult(
        player_id=request.player_id,
        winning_team_id=winner.team_id,
        winning_offer=winner,
        ranked_offers=ranked,
        rationale=" | ".join(rationale_parts),
    )
