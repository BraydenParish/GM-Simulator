import pytest

from app.services.llm import validate_structured_recap


def _context() -> dict:
    return {
        "teams": {"home": "Team A", "away": "Team B"},
        "score": {"home": 24, "away": 17},
        "key_players": [
            {"player_id": 1, "name": "QB One", "line": "20/30 for 250 yds"},
            {"player_id": 2, "name": "RB Two", "line": "18 carries"},
        ],
    }


def test_validate_structured_recap_passes_on_matching_data() -> None:
    context = _context()
    payload = {
        "summary": "Team A wins",
        "scoreboard": {
            "home_team": "Team A",
            "away_team": "Team B",
            "home_score": 24,
            "away_score": 17,
        },
        "notable_players": [
            {"player_id": 1, "fact": "Key throw"},
            {"player_id": 2, "fact": "Big runs"},
        ],
    }

    validate_structured_recap(payload, context)


def test_validate_structured_recap_raises_on_mismatch() -> None:
    context = _context()
    payload = {
        "summary": "Team A wins",
        "scoreboard": {
            "home_team": "Team A",
            "away_team": "Team B",
            "home_score": 31,
            "away_score": 17,
        },
        "notable_players": [
            {"player_id": 1, "fact": "Key throw"},
        ],
    }

    with pytest.raises(ValueError):
        validate_structured_recap(payload, context)
