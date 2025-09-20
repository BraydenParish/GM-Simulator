from pathlib import Path

import pytest

from app.services.ratings_loader import load_player_ratings


def test_load_player_ratings_blends_sources():
    data_dir = Path(__file__).resolve().parents[2] / "data" / "ratings"
    players = load_player_ratings(data_dir)
    players_by_id = {player.player_id: player for player in players}

    assert {1001, 1002, 1003, 1004} <= set(players_by_id.keys())
    qb = players_by_id[1001]
    edge = players_by_id[1003]

    assert qb.name == "Casey Cannon"
    assert qb.pff_grade == pytest.approx(88.5)
    assert 0 <= qb.overall <= 100
    assert edge.pff_grade == pytest.approx(91.2)
    assert edge.overall >= qb.overall - 15
    for rating in players:
        for value in rating.traits.values():
            assert value >= 0
