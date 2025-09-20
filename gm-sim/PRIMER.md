# PRIMER

## What
- Added `OpenRouterClient` to wrap Gemini 2.x Flash on OpenRouter and expose a
  reusable `generate_game_recap` helper.
- Created a Madden/PFF blending pipeline (`ratings_loader`) plus seed CSVs for
  merged player ratings and traits.
- Implemented a deterministic `SeasonSimulator` that generates a round-robin
  schedule, records standings, aggregates player stat lines, and requests LLM
  recaps.
- Added service-layer tests that exercise the ratings loader, LLM wrapper, and
  full season simulation orchestration.

## Why
- The simulator now has modular entry points for integrating narrative flavour
  while preserving deterministic outcomes.
- Blending public Madden and PFF data provides richer baselines for team/unit
  strength calculations and offseason flows.
- A season loop with player stat output is the foundation for roster moves,
  morale systems, and front-office decision modelling.

## Proof
- `pytest -q`
- `ruff check .`
- `black --check .`
- `mypy app`
