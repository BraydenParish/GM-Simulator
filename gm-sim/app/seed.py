import asyncio
import csv
import json
import os

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import engine, AsyncSessionLocal
from app.models import Contract, DepthChart, DraftPick, Player, Team
from app.schemas import ContractSignRequest
from app.services.contracts import build_contract_financials

data_dir = os.path.join(os.path.dirname(__file__), "..", "data", "seed")


async def seed_teams(session: AsyncSession):
    with open(os.path.join(data_dir, "teams.csv"), newline="") as f:
        for row in csv.DictReader(f):
            team = Team(**row)
            session.add(team)
    await session.commit()


async def seed_players(session: AsyncSession):
    with open(os.path.join(data_dir, "players.csv"), newline="") as f:
        for row in csv.DictReader(f):
            player = Player(**row)
            session.add(player)
    await session.commit()


async def seed_contracts(session: AsyncSession):
    with open(os.path.join(data_dir, "contracts.csv"), newline="") as f:
        for row in csv.DictReader(f):
            base_salary = json.loads(row["base_salary_yearly"])
            request = ContractSignRequest(
                player_id=int(row["player_id"]),
                team_id=int(row["team_id"]),
                start_year=int(row["start_year"]),
                end_year=int(row["end_year"]),
                base_salary_yearly={int(k): int(v) for k, v in base_salary.items()},
                signing_bonus_total=int(row["signing_bonus_total"]),
                guarantees_total=int(row["guarantees_total"]),
                no_trade=row.get("no_trade", "false").lower() == "true",
                void_years=int(row.get("void_years", 0) or 0),
            )
            financials = build_contract_financials(request)
            contract = Contract(
                id=int(row["id"]),
                player_id=request.player_id,
                team_id=request.team_id,
                start_year=request.start_year,
                end_year=request.end_year,
                apy=financials.apy,
                base_salary_yearly={
                    str(year): int(amount) for year, amount in financials.base_salary.items()
                },
                signing_bonus_total=request.signing_bonus_total,
                guarantees_total=request.guarantees_total,
                cap_hits_yearly={
                    str(year): int(amount) for year, amount in financials.cap_hits.items()
                },
                dead_money_yearly={
                    str(year): int(amount) for year, amount in financials.dead_money.items()
                },
                no_trade=request.no_trade,
                void_years=request.void_years,
            )
            session.add(contract)
    await session.commit()


async def seed_depth_chart(session: AsyncSession):
    with open(os.path.join(data_dir, "depth_chart.csv"), newline="") as f:
        for row in csv.DictReader(f):
            depth = DepthChart(**row)
            session.add(depth)
    await session.commit()


async def seed_picks(session: AsyncSession):
    with open(os.path.join(data_dir, "picks.csv"), newline="") as f:
        for row in csv.DictReader(f):
            pick = DraftPick(**row)
            session.add(pick)
    await session.commit()


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: __import__("app.models").models.Base.metadata.create_all(bind=c)
        )
    async with AsyncSessionLocal() as session:
        await seed_teams(session)
        await seed_players(session)
        await seed_contracts(session)
        await seed_depth_chart(session)
        await seed_picks(session)
    print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
