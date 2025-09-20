# GM Simulator Backend Overview

## Repository Structure

- `app/`: FastAPI application code.
  - `main.py`: FastAPI application factory and router registration.
  - `db.py`: Async SQLAlchemy engine/session configuration.
  - `models.py`: SQLAlchemy ORM models for teams, players, contracts, depth charts, draft picks, transactions, games, and standings.
  - `routers/`: FastAPI routers grouped by domain (players, teams, etc.).
  - `schemas.py`: Pydantic models shared across routers.
  - `services/`: Domain-specific helpers (e.g., ratings scaffolding).
- `data/`: Seed CSVs and related assets used to bootstrap the database.
- `data/ratings/`: Sample Madden 25 and PFF grade extracts that seed the ratings
  pipeline.
- `tests/`: Automated test suites. Newly added `tests/api/test_players.py` exercises the player listing API end-to-end.
- `pytest.ini`: Pytest configuration enabling asyncio tests.

## Data Model Snapshot

Key SQLAlchemy models:

- `Team`: Core team metadata including scheme hints and cap space.
- `Player`: Player attributes and ratings with an optional FK to `Team`.
- `Contract`, `DepthChart`, `DraftPick`, `Transaction`, `Game`, `Standing`: Additional operational tables for league management.

## API Highlights

- `GET /players/`: Returns a paginated envelope `{items, total, page, page_size}` of player records.
  - Query parameters:
    - `page` (>=1, default 1)
    - `page_size` (1-100, default 25)
    - `team_id` (filter by owning team)
    - `position` (exact position code, case-insensitive)
    - `search` (case-insensitive substring match on player name)
  - Examples and validation errors are documented in the OpenAPI schema.
- Other routers (teams, depth, contracts, picks, transactions, games, standings) expose CRUD-style endpoints built on the shared schemas above.

## Operational Notes for This Run

- `/players/` 500 regression resolved by returning serialized DTOs and enforcing async session usage.
- Pagination and filtering implemented on `/players/`, with comprehensive tests covering success paths and validation failures.
- Async SQLAlchemy session management now uses `async_sessionmaker` to avoid improper generator usage.
- Added a ratings pipeline (`app/services/ratings_loader.py`) that merges Madden 25
  overalls with PFF grades and normalises the blended output to a 0-100 scale.
- Introduced an OpenRouter LLM client and `SeasonSimulator` that stitches together
  round-robin schedules, probabilistic game sims, player stat tracking, and
  narrative recaps produced by Gemini 2.x Flash via OpenRouter.

This document should be kept current as new tables, rules, or endpoints are introduced.
