import asyncio
import csv
import json
import os

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import engine, AsyncSessionLocal
from app.models import Contract, DepthChart, DraftPick, Player, Team

data_dir = os.path.join(os.path.dirname(__file__), "..", "data", "seed")


async def seed_teams_safe(session: AsyncSession):
    """Seed teams only if they don't already exist"""
    with open(os.path.join(data_dir, "teams.csv"), newline="") as f:
        for row in csv.DictReader(f):
            # Check if team already exists
            existing = await session.execute(
                select(Team).where(Team.id == int(row["id"]))
            )
            if not existing.scalar_one_or_none():
                team = Team(**row)
                session.add(team)
                print(f"Added team: {team.name}")
            else:
                print(f"Team {row['name']} already exists, skipping")
    await session.commit()


async def seed_players_safe(session: AsyncSession):
    """Seed players only if they don't already exist"""
    with open(os.path.join(data_dir, "players.csv"), newline="") as f:
        for row in csv.DictReader(f):
            # Check if player already exists
            existing = await session.execute(
                select(Player).where(Player.id == int(row["id"]))
            )
            if not existing.scalar_one_or_none():
                player = Player(**row)
                session.add(player)
                if int(row["id"]) % 50 == 0:  # Print every 50th player
                    print(f"Added player: {player.name}")
            else:
                print(f"Player {row['name']} already exists, skipping")
    await session.commit()


async def seed_contracts_safe(session: AsyncSession):
    """Seed contracts only if they don't already exist"""
    with open(os.path.join(data_dir, "contracts.csv"), newline="") as f:
        for row in csv.DictReader(f):
            # Check if contract already exists
            existing = await session.execute(
                select(Contract).where(Contract.id == int(row["id"]))
            )
            if not existing.scalar_one_or_none():
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


async def seed_depth_chart_safe(session: AsyncSession):
    """Seed depth chart only if it doesn't already exist"""
    with open(os.path.join(data_dir, "depth_chart.csv"), newline="") as f:
        for row in csv.DictReader(f):
            # Check if depth chart entry already exists (composite key)
            existing = await session.execute(
                select(DepthChart).where(
                    DepthChart.team_id == int(row["team_id"]),
                    DepthChart.pos_group == row["pos_group"],
                    DepthChart.slot == int(row["slot"]),
                )
            )
            if not existing.scalar_one_or_none():
                depth = DepthChart(**row)
                session.add(depth)
    await session.commit()


async def seed_picks_safe(session: AsyncSession):
    """Seed draft picks only if they don't already exist"""
    with open(os.path.join(data_dir, "picks.csv"), newline="") as f:
        for row in csv.DictReader(f):
            # Check if pick already exists
            existing = await session.execute(
                select(DraftPick).where(DraftPick.id == int(row["id"]))
            )
            if not existing.scalar_one_or_none():
                pick = DraftPick(**row)
                session.add(pick)
    await session.commit()


async def main():
    print("Starting safe seed process...")

    # Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: __import__("app.models").models.Base.metadata.create_all(bind=c)
        )

    async with AsyncSessionLocal() as session:
        print("Seeding teams...")
        await seed_teams_safe(session)

        print("Seeding players...")
        await seed_players_safe(session)

        print("Seeding contracts...")
        await seed_contracts_safe(session)

        print("Seeding depth chart...")
        await seed_depth_chart_safe(session)

        print("Seeding draft picks...")
        await seed_picks_safe(session)

    print("✅ Safe seed complete!")


if __name__ == "__main__":
    asyncio.run(main())
