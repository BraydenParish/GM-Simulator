from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Contract, Player, Team
from app.schemas import (
    ContractCutRequest,
    ContractCutResponse,
    ErrorResponse,
    ContractRead,
    ContractSignRequest,
)

router = APIRouter(prefix="/contracts", tags=["contracts"])


def _distribute_bonus(total: int, years: int) -> List[int]:
    if years <= 0:
        if total > 0:
            raise HTTPException(
                status_code=422,
                detail="Signing bonus requires at least one proration year",
            )
        return []
    base = total // years
    remainder = total % years
    return [base + (1 if idx < remainder else 0) for idx in range(years)]


def _normalize_year_dict(values: Dict[int, int]) -> Dict[str, int]:
    return {str(year): int(amount) for year, amount in sorted(values.items())}


@router.post(
    "/sign",
    response_model=ContractRead,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def sign_contract(
    payload: ContractSignRequest, db: AsyncSession = Depends(get_db)
) -> ContractRead:
    if payload.end_year < payload.start_year:
        raise HTTPException(status_code=422, detail="End year must be >= start year")

    contract_years = payload.end_year - payload.start_year + 1
    expected_years = {year for year in range(payload.start_year, payload.end_year + 1)}
    provided_years = set(payload.base_salary_yearly.keys())
    if provided_years != expected_years:
        raise HTTPException(
            status_code=422,
            detail="Base salaries must be provided for every contract year",
        )

    team = await db.get(Team, payload.team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    player = await db.get(Player, payload.player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    proration_years = contract_years + max(payload.void_years, 0)
    bonus_shares = _distribute_bonus(payload.signing_bonus_total, proration_years)
    actual_shares = bonus_shares[:contract_years]
    if len(actual_shares) < contract_years:
        actual_shares.extend([0] * (contract_years - len(actual_shares)))
    void_shares = bonus_shares[contract_years:]
    if len(void_shares) < payload.void_years:
        void_shares.extend([0] * (payload.void_years - len(void_shares)))

    cap_hits: Dict[int, int] = {}
    dead_money: Dict[int, int] = {}
    base_salaries = {
        int(year): int(amount) for year, amount in payload.base_salary_yearly.items()
    }
    total_bonus_schedule: List[int] = actual_shares + void_shares

    for idx, year in enumerate(range(payload.start_year, payload.end_year + 1)):
        proration = actual_shares[idx] if idx < len(actual_shares) else 0
        cap_hits[year] = base_salaries[year] + proration
        dead_money[year] = sum(total_bonus_schedule[idx:])

    if payload.void_years:
        for offset in range(payload.void_years):
            share_index = contract_years + offset
            future_year = payload.end_year + offset + 1
            dead_money[future_year] = sum(total_bonus_schedule[share_index:])

    current_cap_hit = cap_hits[payload.start_year]
    if team.cap_space < current_cap_hit:
        raise HTTPException(
            status_code=422, detail="Insufficient cap space to sign player"
        )

    total_value = sum(base_salaries.values()) + payload.signing_bonus_total
    apy = total_value // contract_years

    player.team_id = payload.team_id
    team.cap_space -= current_cap_hit

    contract = Contract(
        player_id=payload.player_id,
        team_id=payload.team_id,
        start_year=payload.start_year,
        end_year=payload.end_year,
        apy=apy,
        base_salary_yearly=_normalize_year_dict(base_salaries),
        signing_bonus_total=payload.signing_bonus_total,
        guarantees_total=payload.guarantees_total,
        cap_hits_yearly=_normalize_year_dict(cap_hits),
        dead_money_yearly=_normalize_year_dict(dead_money),
        no_trade=payload.no_trade,
        void_years=payload.void_years,
    )

    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    return ContractRead.model_validate(contract)


@router.post(
    "/cut",
    response_model=ContractCutResponse,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def cut_contract(
    payload: ContractCutRequest, db: AsyncSession = Depends(get_db)
) -> ContractCutResponse:
    contract_result = await db.execute(
        select(Contract).where(
            Contract.player_id == payload.player_id,
            Contract.team_id == payload.team_id,
        )
    )
    contract = contract_result.scalar_one_or_none()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    team = await db.get(Team, payload.team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    player = await db.get(Player, payload.player_id)

    year_key = str(payload.league_year)
    if year_key not in contract.cap_hits_yearly:
        raise HTTPException(
            status_code=422, detail="No cap hit recorded for the requested year"
        )

    cap_hit = int(contract.cap_hits_yearly[year_key])
    base_salary = int(contract.base_salary_yearly.get(year_key, 0))
    proration_current = cap_hit - base_salary
    remaining_dead = int(contract.dead_money_yearly.get(year_key, 0))

    if payload.post_june1:
        dead_current = proration_current
        future_dead = max(0, remaining_dead - proration_current)
    else:
        dead_current = remaining_dead
        future_dead = 0

    freed_cap = cap_hit - dead_current
    team.cap_space += freed_cap

    if player:
        player.team_id = None

    await db.delete(contract)
    await db.commit()

    return ContractCutResponse(
        dead_money_current=dead_current,
        dead_money_future=future_dead,
        cap_space=team.cap_space,
        freed_cap=freed_cap,
    )
