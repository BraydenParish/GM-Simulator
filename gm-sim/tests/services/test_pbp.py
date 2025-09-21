import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.services.pbp import derive_ratings, load_rows, write_output


def _sample_rows():
    return [
        {
            "posteam": "ALP",
            "passer_player_id": "QB1",
            "passer_player_name": "Alpha QB",
            "receiver_player_id": "WR1",
            "receiver_player_name": "Alpha WR",
            "epa": "0.7",
            "yards_gained": "25",
            "complete_pass": "1",
        },
        {
            "posteam": "BET",
            "passer_player_id": "QB2",
            "passer_player_name": "Beta QB",
            "receiver_player_id": "WR2",
            "receiver_player_name": "Beta WR",
            "epa": "0.1",
            "yards_gained": "6",
            "complete_pass": "0",
        },
        {
            "posteam": "ALP",
            "rusher_player_id": "RB1",
            "rusher_player_name": "Alpha RB",
            "epa": "0.3",
            "yards_gained": "8",
        },
        {
            "posteam": "ALP",
            "rusher_player_id": "RB1",
            "rusher_player_name": "Alpha RB",
            "epa": "-0.1",
            "yards_gained": "2",
        },
        {
            "posteam": "BET",
            "rusher_player_id": "RB2",
            "rusher_player_name": "Beta RB",
            "epa": "0.05",
            "yards_gained": "4",
        },
    ]


def test_derive_ratings_scales_outputs():
    rows = _sample_rows()
    result = derive_ratings(rows)

    assert len(result.quarterbacks) == 2
    assert result.quarterbacks[0].player_id == "QB1"
    assert result.quarterbacks[0].rating > result.quarterbacks[1].rating

    assert len(result.rushers) == 2
    assert result.rushers[0].player_id == "RB1"
    assert result.rushers[0].rating >= result.rushers[1].rating

    assert len(result.receivers) == 2
    assert result.receivers[0].player_id == "WR1"
    assert result.summary["quarterbacks"]["count"] == 2.0
    assert result.summary["rushers"]["count"] == 2.0
    assert result.summary["receivers"]["count"] == 2.0


def test_load_rows_and_write_output(tmp_path):
    rows = _sample_rows()
    source_path = tmp_path / "pbp.csv"
    with source_path.open("w", encoding="utf-8") as handle:
        headers = [
            "posteam",
            "passer_player_id",
            "passer_player_name",
            "receiver_player_id",
            "receiver_player_name",
            "rusher_player_id",
            "rusher_player_name",
            "epa",
            "yards_gained",
            "complete_pass",
        ]
        handle.write(",".join(headers) + "\n")
        for row in rows:
            ordered = [str(row.get(column, "")) for column in headers]
            handle.write(",".join(ordered) + "\n")

    loaded = load_rows(source_path)
    assert len(loaded) == len(rows)

    output_dir = tmp_path / "out"
    write_output(loaded, output_dir)

    for filename in [
        "quarterbacks.json",
        "rushers.json",
        "receivers.json",
        "summary.json",
    ]:
        path = output_dir / filename
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data
