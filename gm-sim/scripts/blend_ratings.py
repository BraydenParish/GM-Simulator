"""CLI helper to blend Madden, PFF, and play-by-play ratings."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.services.pbp import derive_ratings, load_rows
from app.services.rating_blender import (
    RatingSourceWeights,
    blend_ratings,
    load_madden_ratings,
    load_pff_grades,
    pbp_ratings_map,
    write_blended_output,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Blend multiple rating sources")
    parser.add_argument("madden", type=Path, help="Path to Madden ratings CSV")
    parser.add_argument("pff", type=Path, help="Path to PFF grades CSV")
    parser.add_argument("pbp", type=Path, help="Path to nflfastR-style play data (CSV/JSON)")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/ratings/blended_ratings.json"),
        help="Destination JSON file",
    )
    parser.add_argument(
        "--weights",
        type=float,
        nargs=3,
        metavar=("MADDEN", "PFF", "PBP"),
        help="Override rating weights (defaults 0.5 0.3 0.2)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    madden = load_madden_ratings(args.madden)
    pff = load_pff_grades(args.pff)
    rows = load_rows(args.pbp)
    pbp_output = derive_ratings(rows)
    pbp_map = pbp_ratings_map(pbp_output)
    if args.weights:
        weights = RatingSourceWeights(*args.weights)
    else:
        weights = RatingSourceWeights()
    blended = blend_ratings(madden, pff, pbp_map, weights=weights)
    write_blended_output(blended, args.output)
    print(
        f"Blended {len(blended)} players into {args.output} with weights "
        f"Madden={weights.madden} PFF={weights.pff} PBP={weights.pbp}"
    )


if __name__ == "__main__":
    main()
