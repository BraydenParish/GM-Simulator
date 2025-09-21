"""CLI helper to aggregate nflfastR-style play-by-play extracts.

Usage:
    python scripts/import_pbp.py --source data/pbp/sample.csv --output data/pbp/ratings

The script delegates to :mod:`app.services.pbp` for the heavy lifting and
writes JSON artefacts (quarterbacks.json, rushers.json, receivers.json,
summary.json) that downstream tooling can consume.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.services.pbp import load_rows, write_output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate nflfastR play-by-play data")
    parser.add_argument(
        "--source", required=True, help="Path to the play-by-play CSV/JSON extract"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Directory to write aggregated JSON files (created if missing)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = load_rows(Path(args.source))
    write_output(rows, Path(args.output))


if __name__ == "__main__":
    main()
