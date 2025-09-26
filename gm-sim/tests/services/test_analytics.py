from app.services.analytics import compute_drive_analytics


def test_compute_drive_analytics_returns_epa_and_summary() -> None:
    drives = [
        {"team": "home", "result": "TD", "yards": 80, "minutes": 2.4},
        {"team": "away", "result": "FG", "yards": 48, "minutes": 3.1},
        {"team": "home", "result": "Punt", "yards": 35, "minutes": 2.0},
        {"team": "away", "result": "Turnover", "yards": -2, "minutes": 1.2},
    ]

    payload = compute_drive_analytics(drives=drives, home_score=27, away_score=16)

    assert "drives" in payload and len(payload["drives"]) == len(drives)
    assert payload["drives"][0]["points"] == 7
    assert payload["drives"][0]["epa"] != 0
    assert payload["summary"]["home"]["final_score"] == 27
    assert payload["summary"]["away"]["final_score"] == 16
    assert payload["summary"]["explosive_plays"] >= 1


def test_compute_drive_analytics_handles_empty_drives() -> None:
    payload = compute_drive_analytics(drives=[], home_score=21, away_score=20)
    assert payload["drives"] == []
    assert payload["summary"]["home"]["final_score"] == 21
    assert payload["summary"]["away"]["final_score"] == 20
