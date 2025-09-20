import random

import pytest

from app.services.injuries import InjuryEngine, PlayerParticipation


def build_sample_roster() -> list[PlayerParticipation]:
    positions = (
        ["QB"]
        + ["RB", "WR", "WR", "TE"]
        + ["OL"] * 5
        + ["DL"] * 4
        + ["EDGE"] * 4
        + ["LB"] * 4
        + ["CB"] * 4
        + ["S"] * 4
        + ["K", "P"]
    )
    roster = []
    for idx, pos in enumerate(positions, start=1):
        roster.append(PlayerParticipation(player_id=idx, position=pos, snaps=55))
    return roster


def test_injury_engine_generates_reasonable_injury_counts():
    rng = random.Random(1234)
    engine = InjuryEngine(rng=rng)
    roster = build_sample_roster()

    total_injuries = 0
    games = 60
    for _ in range(games):
        total_injuries += len(engine.simulate_game(team_id=1, participants=roster))
        engine.rest_week({1: roster})

    avg_injuries = total_injuries / games
    assert 0.5 <= avg_injuries <= 4.0


def test_fatigue_reduces_effective_snaps():
    player = PlayerParticipation(player_id=1, position="RB", snaps=60)
    baseline = player.active_snaps()
    player.fatigue = 90.0
    fatigued = player.active_snaps()
    assert fatigued < baseline
    assert fatigued >= int(player.snaps * 0.35)


@pytest.mark.parametrize(
    "fatigue, expected_penalty",
    [(0.0, 0.0), (70.0, pytest.approx(1.0, rel=0.2))],
)
def test_team_availability_penalty_scales_with_fatigue(fatigue, expected_penalty):
    engine = InjuryEngine(rng=random.Random(7))
    roster = [PlayerParticipation(player_id=1, position="WR", snaps=50, fatigue=fatigue)]
    penalty = engine.team_availability_penalty(roster)
    assert penalty >= 0.0
    if fatigue > 0:
        assert penalty > 0.0
        assert penalty == pytest.approx(expected_penalty, rel=1.0)
