import json
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models import Base, Player
from app.services.pbp import RatingEntry, RatingsOutput
from app.services.rating_blender import (
    RatingSourceWeights,
    apply_blended_ratings,
    blend_ratings,
    pbp_ratings_map,
    write_blended_output,
)


def test_pbp_ratings_map_from_output(tmp_path: Path) -> None:
    output = RatingsOutput(
        quarterbacks=[
            RatingEntry(
                player_id="QB1",
                player_name="Alpha QB",
                team="ALP",
                attempts=10,
                secondary=0,
                yards=120.0,
                epa=4.5,
                efficiency_primary=0.4,
                efficiency_secondary=0.2,
                rating=82.5,
            )
        ],
        rushers=[
            RatingEntry(
                player_id="RB1",
                player_name="Alpha RB",
                team="ALP",
                attempts=15,
                secondary=2,
                yards=80.0,
                epa=1.1,
                efficiency_primary=0.32,
                efficiency_secondary=0.18,
                rating=74.0,
            )
        ],
        receivers=[],
        summary={},
    )
    mapping = pbp_ratings_map(output)
    assert mapping == {"QB1": 82.5, "RB1": 74.0}


def test_blend_ratings_with_weighted_sources(tmp_path: Path) -> None:
    madden = {"1": 88.0, "2": 70.0}
    pff = {"1": 90.0}
    pbp = {"1": 72.0, "2": 66.0}
    blended = blend_ratings(madden, pff, pbp)
    assert pytest.approx(blended["1"].rating, rel=1e-3) == 85.4
    assert pytest.approx(blended["1"].confidence, rel=1e-3) == 1.0
    assert blended["1"].weight_share == pytest.approx(
        {"madden": 0.5, "pff": 0.3, "pbp": 0.2}
    )
    write_path = tmp_path / "blended.json"
    write_blended_output(blended, write_path)
    data = json.loads(write_path.read_text(encoding="utf-8"))
    assert any(entry["player_id"] == "1" for entry in data)


def test_blend_ratings_with_missing_sources() -> None:
    blended = blend_ratings({}, {}, {"2": 65.0})
    assert pytest.approx(blended["2"].rating, rel=1e-6) == 65.0
    assert pytest.approx(blended["2"].confidence, rel=1e-6) == 0.2
    assert blended["2"].weight_share == {"pbp": 1.0}


@pytest.mark.asyncio
async def test_apply_blended_ratings_updates_players(tmp_path: Path) -> None:
    db_path = tmp_path / "ratings.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}", future=True, poolclass=NullPool
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        session.add_all(
            [
                Player(id=1, name="Alpha QB", pos="QB"),
                Player(id=2, name="Beta RB", pos="RB"),
            ]
        )
        await session.commit()

    weights = RatingSourceWeights()
    blended = blend_ratings(
        {"1": 88.0},
        {"1": 90.0},
        {"1": 70.0, "2": 65.0},
        weights=weights,
    )

    async with session_factory() as session:
        await apply_blended_ratings(session, blended)
        await session.commit()

    async with session_factory() as session:
        player_one = await session.get(Player, 1)
        player_two = await session.get(Player, 2)

    assert player_one is not None
    assert (
        pytest.approx(player_one.blended_rating, rel=1e-6)
        == (88.0 * weights.madden + 90.0 * weights.pff + 70.0 * weights.pbp)
        / weights.total
    )
    assert pytest.approx(player_one.rating_confidence, rel=1e-6) == 1.0
    assert pytest.approx(player_one.madden_rating, rel=1e-6) == 88.0
    assert pytest.approx(player_one.pff_grade, rel=1e-6) == 90.0
    assert pytest.approx(player_one.pbp_rating, rel=1e-6) == 70.0
    assert (
        pytest.approx(player_one.rating_components["madden"]["weight"], rel=1e-6)
        == weights.madden / weights.total
    )

    assert player_two is not None
    assert pytest.approx(player_two.blended_rating, rel=1e-6) == 65.0
    assert pytest.approx(player_two.rating_confidence, rel=1e-6) == (
        weights.pbp / weights.total
    )
    assert player_two.rating_components["pbp"]["weight"] == pytest.approx(1.0)
    assert pytest.approx(player_two.pbp_rating, rel=1e-6) == 65.0

    await engine.dispose()
