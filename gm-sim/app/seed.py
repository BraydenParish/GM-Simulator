import asyncio
import csv
import json
import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import engine, AsyncSessionLocal
from app.models import Contract, DepthChart, DraftPick, Player, Team
from app.schemas import ContractSignRequest
from app.services.contracts import build_contract_financials

data_dir = os.path.join(os.path.dirname(__file__), "..", "data", "seed")


async def seed_teams(session: AsyncSession):
    with open(os.path.join(data_dir, "teams.csv"), newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            team_id = int(row["id"])
            # Check if exists
            existing = await session.execute(select(Team).where(Team.id == team_id))
            if existing.scalars().first() is not None:
                # Skip or maybe update if needed
                continue

            team = Team(
                id=team_id,
                name=row["name"],
                abbr=row["abbr"],
                conference=row["conference"],
                division=row["division"],
                elo=float(row["elo"]),
                scheme_off=row["scheme_off"],
                scheme_def=row["scheme_def"],
                cap_space=int(row["cap_space"]),
                cap_year=int(row["cap_year"]),
            )
            session.add(team)
        await session.commit()


async def seed_players(session: AsyncSession):
    with open(os.path.join(data_dir, "players.csv"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            player_id = int(row["id"])
            # Check if exists
            existing = await session.execute(select(Player).where(Player.id == player_id))
            if existing.scalars().first() is not None:
                # Skip this player
                continue

            player = Player(
                id=player_id,
                name=row["name"],
                pos=row["pos"],
                team_id=int(row["team_id"]) if row["team_id"] else None,
                age=int(row["age"]) if row.get("age") else None,
                height=int(row["height"]) if row.get("height") else None,
                weight=int(row["weight"]) if row.get("weight") else None,
                ovr=int(row["ovr"]) if row.get("ovr") else None,
                pot=int(row["pot"]) if row.get("pot") else None,
                spd=int(row["spd"]) if row.get("spd") else None,
                acc=int(row["acc"]) if row.get("acc") else None,
                agi=int(row["agi"]) if row.get("agi") else None,
                str=int(row["str"]) if row.get("str") else None,
                awr=int(row["awr"]) if row.get("awr") else None,
                injury_status=row.get("injury_status", "OK"),
                morale=int(row["morale"]) if row.get("morale") else 50,
                stamina=int(row["stamina"]) if row.get("stamina") else 80,
                thp=int(row["thp"]) if row.get("thp") else None,
                tha_s=int(row["tha_s"]) if row.get("tha_s") else None,
                tha_m=int(row["tha_m"]) if row.get("tha_m") else None,
                tha_d=int(row["tha_d"]) if row.get("tha_d") else None,
                tup=int(row["tup"]) if row.get("tup") else None,
            )
            session.add(player)

    await session.commit()


async def seed_contracts(session: AsyncSession):
    bad_count = 0
    with open(os.path.join(data_dir, "contracts.csv"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            raw = row.get("base_salary_yearly", "")
            try:
                base_salary = json.loads(raw)
            except json.JSONDecodeError as e:
                logging.warning(f"JSON decode error in seed_contracts for id={row.get('id')}: {e}; raw data: {raw!r}")
                # Try a fallback attempt if you think raw uses single quotes
                try:
                    alt = raw.replace("'", "\"")
                    base_salary = json.loads(alt)
                except json.JSONDecodeError as e2:
                    logging.error(f"Fallback also failed for id={row.get('id')}: {e2}")
                    bad_count += 1
                    continue  # skip this row or handle default
            
            # Now safe to use base_salary
            # rest as before:
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
    logging.info(f"seed_contracts complete, skipped {bad_count} bad rows")


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
