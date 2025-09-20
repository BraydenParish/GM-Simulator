import asyncio
import csv
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db import engine, AsyncSessionLocal
from app.models import Team, Player, Contract, DepthChart, DraftPick

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
            contract = Contract(**row)
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
