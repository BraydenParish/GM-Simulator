import pytest

from app.services.playoffs import PlayoffSeed, PlayoffSimulator


@pytest.mark.asyncio
async def test_playoff_simulator_runs_bracket() -> None:
    seeds = [
        PlayoffSeed(
            seed=1,
            team_id=1,
            name="Alpha",
            abbr="ALP",
            rating=1650,
            wins=13,
            losses=4,
            ties=0,
            points_for=420,
            points_against=280,
        ),
        PlayoffSeed(
            seed=2,
            team_id=2,
            name="Bravo",
            abbr="BRV",
            rating=1600,
            wins=12,
            losses=5,
            ties=0,
            points_for=395,
            points_against=300,
        ),
        PlayoffSeed(
            seed=3,
            team_id=3,
            name="Charlie",
            abbr="CHL",
            rating=1525,
            wins=11,
            losses=6,
            ties=0,
            points_for=360,
            points_against=315,
        ),
        PlayoffSeed(
            seed=4,
            team_id=4,
            name="Delta",
            abbr="DLT",
            rating=1480,
            wins=10,
            losses=7,
            ties=0,
            points_for=340,
            points_against=330,
        ),
    ]

    simulator = PlayoffSimulator(seeds, rng_seed=12345)
    games = await simulator.simulate()

    assert len(games) == 3  # two semifinals plus championship
    round_names = {game.round_name for game in games}
    assert {"Semifinals", "Championship"}.issubset(round_names)

    champion = simulator.champion()
    assert champion.team_id in {seed.team_id for seed in seeds}


def test_playoff_simulator_requires_power_of_two() -> None:
    seeds = [
        PlayoffSeed(
            seed=1,
            team_id=1,
            name="Alpha",
            abbr="ALP",
            rating=1650,
            wins=13,
            losses=4,
            ties=0,
            points_for=420,
            points_against=280,
        ),
        PlayoffSeed(
            seed=2,
            team_id=2,
            name="Bravo",
            abbr="BRV",
            rating=1600,
            wins=12,
            losses=5,
            ties=0,
            points_for=395,
            points_against=300,
        ),
        PlayoffSeed(
            seed=3,
            team_id=3,
            name="Charlie",
            abbr="CHL",
            rating=1525,
            wins=11,
            losses=6,
            ties=0,
            points_for=360,
            points_against=315,
        ),
    ]

    with pytest.raises(ValueError):
        PlayoffSimulator(seeds)
