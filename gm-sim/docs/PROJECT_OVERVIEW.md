# GM Simulator Backend Overview

## Repository Structure

- `app/`: FastAPI application code.
  - `main.py`: FastAPI application factory and router registration.
  - `db.py`: Async SQLAlchemy engine/session configuration.
  - `models.py`: SQLAlchemy ORM models for teams, players, contracts, depth charts, draft picks, transactions, games, standings, practice-squad assignments, and gameday submissions.
  - `routers/`: FastAPI routers grouped by domain (players, teams, roster rules, etc.).
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
- `Contract`: Stores base salaries, signing-bonus proration, yearly cap hits,
  dead-money schedules, void years, and no-trade clauses for each agreement.
- `SalaryCap`: Captures the league-wide cap baseline and optional team rollovers
  for each season.
- `DepthChart`, `DraftPick`, `Transaction`, `Game`, `Standing`: Additional
  operational tables for league management. Draft picks now include a `used`
  flag so spent assets disappear from future trade or draft calculations.
- `PracticeSquad`: Tracks practice-squad assignments, IPP designation, and cumulative elevations per player.
- `GamedayRoster`: Persists actives/inactives submissions per game alongside elevated players and offensive line counts.
- `RosterRule`: Key/value store for tunable roster limits.
- `Injury`: Tracks injuries generated during simulations, including severity,
  time missed, and linkage back to the source game.
- `PlayerStamina`: Maintains rolling fatigue for each player so long-term snap
  management can influence future availability.
- `FranchiseState`: Centralised franchise progress tracker persisting the
  current season/week, roster snapshots keyed by team/player ID, the active
  free-agent pool, consumed draft picks, and recent trades.

## API Highlights

- `GET /players/`: Returns a paginated envelope `{items, total, page, page_size}` of player records.
  - Query parameters:
    - `page` (>=1, default 1)
    - `page_size` (1-100, default 25)
    - `team_id` (filter by owning team)
    - `position` (exact position code, case-insensitive)
    - `search` (case-insensitive substring match on player name)
  - Examples and validation errors are documented in the OpenAPI schema.
- `POST /roster/practice-squad/assign`: Adds a player to the practice squad while enforcing the 16 + 1 IPP slot limits and duplicate checks.
- `POST /roster/gameday/set-actives`: Validates and stores gameday actives/inactives, enforcing 53-man totals, the 48/47 offensive-line rule, and practice-squad elevation caps.
- `POST /contracts/sign`: Computes proration, cap hits, and dead-money schedules while ensuring teams have the cap space to sign.
- `POST /contracts/cut`: Applies pre- or post-June-1 logic to determine current/future dead money and adjusts team cap space.
- Other routers (teams, depth, picks, transactions, games, standings) expose CRUD-style endpoints built on the shared schemas above.

## Operational Notes for This Run

- `/players/` 500 regression resolved by returning serialized DTOs and enforcing async session usage.
- Pagination and filtering implemented on `/players/`, with comprehensive tests covering success paths and validation failures.
- Async SQLAlchemy session management now uses `async_sessionmaker` to avoid improper generator usage.
- Added a roster-rules service (`app/services/roster_rules.py`) plus API coverage to enforce 53-man rosters, practice-squad capacity, IPP slot limits, and elevation caps with dedicated regression tests.
- Added a ratings pipeline (`app/services/ratings_loader.py`) that merges Madden 25
  overalls with PFF grades and normalises the blended output to a 0-100 scale.
- Introduced an injury and fatigue engine (`app/services/injuries.py`) now wired
  into the season simulator to generate weekly injury reports, accumulate player
  fatigue, and apply rating penalties to shorthanded teams. Outputs feed new
  `Injury`/`PlayerStamina` tables for persistence and analytics.
- Introduced an OpenRouter LLM client and `SeasonSimulator` that stitches together
  round-robin schedules, probabilistic game sims, player stat tracking, and
  narrative recaps produced by Grok-4-Fast via OpenRouter with automatic fallbacks
  to Gemini 2.5 Flash and Gemini 2.0 Flash Lite whenever Grok is throttled. Each
  narrative prompt now embeds a quick summary of completed simulation tasks and the
  remaining schedule to preserve long-horizon context for the model. Recaps now
  return structured JSON payloads that must pass fact validation against the
  scoreboard/player stats to guard against hallucinations.
- Added a persistent `GameStateStore` service that snapshots rosters, free agents,
  used draft picks, and trade history into the new `FranchiseState` table. The
  season simulator hydrates PlayerParticipation objects from this state, ensures
  participant names/IDs are propagated into game stats, and feeds abridged
  snapshots into narrative prompts as lightweight RAG context.
- Added `app/services/contracts.py` plus `/contracts/sign` and `/contracts/cut`
  endpoints that model signing-bonus proration, guarantee allocation, dead-money
  schedules, and cap-space enforcement with accompanying unit + async API tests.

This document should be kept current as new tables, rules, or endpoints are introduced.
