import asyncio
import csv
import json
import os

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import engine, AsyncSessionLocal
from app.models import Contract, DepthChart, DraftPick, Player, Team

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
            contract_data = {
                "id": int(row["id"]),
                "player_id": int(row["player_id"]),
                "team_id": int(row["team_id"]),
                "start_year": int(row["start_year"]),
                "end_year": int(row["end_year"]),
                "apy": int(row["apy"]),
                "base_salary_yearly": json.loads(row["base_salary_yearly"]),
                "signing_bonus_total": int(row["signing_bonus_total"]),
                "guarantees_total": int(row["guarantees_total"]),
                "cap_hits_yearly": json.loads(row["cap_hits_yearly"]),
                "dead_money_yearly": json.loads(row["dead_money_yearly"]),
                "no_trade": row["no_trade"].lower() == "true",
                "void_years": int(row["void_years"]),
            }
            contract = Contract(**contract_data)
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
