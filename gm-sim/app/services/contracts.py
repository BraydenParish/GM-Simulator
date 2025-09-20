"""Salary cap and contract helper utilities."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Contract, Player, Team
from app.schemas import ContractCutRequest, ContractSignRequest


@dataclass(slots=True)
class ContractFinancials:
    apy: float
    cap_hits: Dict[int, int]
    dead_money: Dict[int, int]
    proration_schedule: Dict[int, int]
    guarantee_allocation: Dict[int, int]
    base_salary: OrderedDict[int, int]


def _serialize_schedule(schedule: Dict[int, int]) -> Dict[str, int]:
    return {str(year): int(amount) for year, amount in schedule.items()}


def _deserialize_schedule(raw: Dict | None) -> Dict[int, int]:
    if not raw:
        return {}
    return {int(year): int(amount) for year, amount in raw.items()}


def _ordered_salary_schedule(
    start_year: int, end_year: int, base_salary: Dict[int, int]
) -> OrderedDict[int, int]:
    years = list(range(start_year, end_year + 1))
    try:
        return OrderedDict((year, int(base_salary[year])) for year in years)
    except KeyError as exc:  # pragma: no cover - validation should prevent this
        raise HTTPException(
            status_code=422, detail="Missing salary entry for contract year"
        ) from exc


def _compute_proration(
    signing_bonus_total: int, start_year: int, end_year: int, void_years: int
) -> Dict[int, int]:
    if signing_bonus_total <= 0:
        return {}
    contract_years = list(range(start_year, end_year + 1))
    proration_years = contract_years + [end_year + i for i in range(1, void_years + 1)]
    total_years = len(proration_years)
    if total_years == 0:
        return {}
    base_amount, remainder = divmod(signing_bonus_total, total_years)
    schedule: Dict[int, int] = {}
    for idx, year in enumerate(proration_years):
        schedule[year] = base_amount + (1 if idx < remainder else 0)
    return schedule


def _allocate_guarantees(
    base_salary: "OrderedDict[int, int]", guarantees_total: int
) -> Dict[int, int]:
    allocation: Dict[int, int] = {}
    remaining = max(0, guarantees_total)
    for year, salary in base_salary.items():
        if remaining <= 0:
            allocation[year] = 0
            continue
        guaranteed = min(salary, remaining)
        allocation[year] = guaranteed
        remaining -= guaranteed
    if remaining > 0 and base_salary:
        first_year = next(iter(base_salary))
        allocation[first_year] = allocation.get(first_year, 0) + remaining
    return allocation


def _build_dead_money_schedule(
    base_salary: "OrderedDict[int, int]",
    proration_schedule: Dict[int, int],
    guarantees: Dict[int, int],
    end_year: int,
    void_years: int,
) -> Dict[int, int]:
    all_proration_years = sorted(proration_schedule)
    dead_money: Dict[int, int] = {}
    for year in base_salary:
        remaining_proration = sum(
            proration_schedule[pr_year] for pr_year in all_proration_years if pr_year >= year
        )
        dead_money[year] = guarantees.get(year, 0) + remaining_proration
    for idx in range(1, void_years + 1):
        year = end_year + idx
        remaining_proration = sum(
            proration_schedule[pr_year] for pr_year in all_proration_years if pr_year >= year
        )
        dead_money[year] = remaining_proration
    return dead_money


def build_contract_financials(request: ContractSignRequest) -> ContractFinancials:
    base_salary = _ordered_salary_schedule(
        request.start_year, request.end_year, request.base_salary_yearly
    )
    proration_schedule = _compute_proration(
        request.signing_bonus_total, request.start_year, request.end_year, request.void_years
    )
    cap_hits: Dict[int, int] = {}
    for year, salary in base_salary.items():
        cap_hits[year] = salary + proration_schedule.get(year, 0)
    total_cash = sum(base_salary.values()) + max(0, request.signing_bonus_total)
    duration = max(1, len(base_salary))
    apy = total_cash / duration
    guarantees = _allocate_guarantees(base_salary, request.guarantees_total)
    dead_money = _build_dead_money_schedule(
        base_salary, proration_schedule, guarantees, request.end_year, request.void_years
    )
    return ContractFinancials(
        apy=apy,
        cap_hits=cap_hits,
        dead_money=dead_money,
        proration_schedule=proration_schedule,
        guarantee_allocation=guarantees,
        base_salary=base_salary,
    )


async def sign_contract(db: AsyncSession, request: ContractSignRequest) -> Contract:
    team = await db.get(Team, request.team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    player = await db.get(Player, request.player_id)
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    financials = build_contract_financials(request)
    first_year_hit = financials.cap_hits.get(request.start_year, 0)
    available_cap = team.cap_space or 0
    if available_cap - first_year_hit < 0:
        raise HTTPException(status_code=422, detail="Insufficient cap space for signing")

    contract = Contract(
        player_id=request.player_id,
        team_id=request.team_id,
        start_year=request.start_year,
        end_year=request.end_year,
        apy=financials.apy,
        base_salary_yearly=_serialize_schedule(dict(financials.base_salary)),
        signing_bonus_total=request.signing_bonus_total,
        guarantees_total=request.guarantees_total,
        cap_hits_yearly=_serialize_schedule(financials.cap_hits),
        dead_money_yearly=_serialize_schedule(financials.dead_money),
        no_trade=request.no_trade,
        void_years=request.void_years,
    )

    team.cap_space = available_cap - first_year_hit
    player.team_id = team.id

    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    return contract


async def cut_contract(db: AsyncSession, request: ContractCutRequest) -> Dict[str, int]:
    contract = await db.get(Contract, request.contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")

    team = await db.get(Team, contract.team_id)
    if team is None:  # pragma: no cover - data integrity
        raise HTTPException(status_code=404, detail="Team not found")

    base_salary = _ordered_salary_schedule(
        contract.start_year,
        contract.end_year,
        _deserialize_schedule(contract.base_salary_yearly),
    )
    proration_schedule = _compute_proration(
        contract.signing_bonus_total, contract.start_year, contract.end_year, contract.void_years
    )
    guarantees = _allocate_guarantees(base_salary, contract.guarantees_total)
    cap_hits = _deserialize_schedule(contract.cap_hits_yearly)

    if request.league_year < contract.start_year or request.league_year > contract.end_year:
        raise HTTPException(status_code=422, detail="League year outside contract term")

    cap_hit = cap_hits.get(request.league_year)
    if cap_hit is None:
        raise HTTPException(status_code=422, detail="No scheduled cap hit for requested year")

    proration_current = proration_schedule.get(request.league_year, 0)
    remaining_future_proration = sum(
        amount for year, amount in proration_schedule.items() if year > request.league_year
    )

    if request.post_june1:
        dead_current = guarantees.get(request.league_year, 0) + proration_current
        dead_next = remaining_future_proration
    else:
        dead_current = (
            guarantees.get(request.league_year, 0) + proration_current + remaining_future_proration
        )
        dead_next = 0

    cap_savings = cap_hit - dead_current
    team.cap_space = (team.cap_space or 0) + cap_savings

    player = await db.get(Player, contract.player_id)
    if player is not None and player.team_id == team.id:
        player.team_id = None

    await db.delete(contract)
    await db.commit()

    return {
        "contract_id": contract.id,
        "league_year": request.league_year,
        "dead_money_current_year": dead_current,
        "dead_money_next_year": dead_next,
        "cap_savings": cap_savings,
        "team_cap_space": team.cap_space or 0,
    }
