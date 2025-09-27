from __future__ import annotations

from typing import Any, Dict, List

_HIGHLIGHT_RESULTS = {"TD", "Turnover"}


def summarize_drives(drives: List[Dict[str, Any]], max_highlights: int = 6) -> List[Dict[str, Any]]:
    """Extract memorable plays from a list of drive dictionaries."""

    highlights: List[Dict[str, Any]] = []
    if not drives:
        return highlights

    for index, drive in enumerate(drives):
        result = str(drive.get("result", "")).strip()
        yards = int(drive.get("yards", 0) or 0)
        minutes = float(drive.get("minutes", 0.0) or 0.0)
        team = drive.get("team")
        if result in _HIGHLIGHT_RESULTS or yards >= 50:
            descriptor = "touchdown" if result == "TD" else result.lower()
            summary = {
                "team": team,
                "result": result,
                "descriptor": descriptor,
                "yards": yards if yards > 0 else None,
                "clock_minutes": round(minutes, 1) if minutes else None,
                "drive_index": index,
            }
            highlights.append(summary)
        if len(highlights) >= max_highlights:
            break

    if not highlights:
        top_drive = max(drives, key=lambda entry: int(entry.get("yards", 0) or 0))
        highlights.append(
            {
                "team": top_drive.get("team"),
                "result": top_drive.get("result"),
                "descriptor": "chunk play",
                "yards": int(top_drive.get("yards", 0) or 0),
                "clock_minutes": float(top_drive.get("minutes", 0.0) or 0.0),
                "drive_index": drives.index(top_drive),
            }
        )
    return highlights
