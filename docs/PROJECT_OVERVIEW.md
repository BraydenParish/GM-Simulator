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
- `Player`: Player attributes and ratings with an optional FK to `Team` plus a `rookie_year` flag for generated draft classes.
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
- `GET /health/injuries`: Returns stored injuries with optional filters for
  `team_id`, `severity`, and an `active_only` toggle to include recovered
  players. Each record includes player/team metadata plus weeks remaining.
- `GET /health/summary`: Aggregates team-level health by combining active
  injury counts with fatigue data from `PlayerStamina`, surfacing severe cases,
  average fatigue, and the number of players above the fatigue threshold.
- `POST /roster/practice-squad/assign`: Adds a player to the practice squad while enforcing the 16 + 1 IPP slot limits and duplicate checks.
- `POST /roster/gameday/set-actives`: Validates and stores gameday actives/inactives, enforcing 53-man totals, the 48/47 offensive-line rule, and practice-squad elevation caps.
- `POST /contracts/sign`: Computes proration, cap hits, and dead-money schedules while ensuring teams have the cap space to sign.
- `POST /contracts/cut`: Applies pre- or post-June-1 logic to determine current/future dead money and adjusts team cap space.
- `POST /contracts/negotiate`: Evaluates proposed free-agent offers, returning APY, guarantee percentage, signing-bonus proration,
  and optional Grok-4-Fast generated negotiation narratives when a narrative client is configured.
- `POST /draft/generate-class`: Generates a deterministic rookie class for a season, supports custom position weights, and persists rookies with `rookie_year` metadata while preventing duplicate class creation.
- `POST /transactions/evaluate-trade`: Returns Jimmy Johnson draft value totals
  for both sides and, when requested, a Grok-4-Fast generated negotiation
  summary including each club's stance and actionable follow-ups.
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
- Added standings tie-breakers (win%, head-to-head, point differential, points
  scored) plus a bracketed postseason simulator that seeds the top clubs,
  generates conference championships and a Super Bowl round, and exposes
  `SeasonSimulator.ranked_teams()` alongside postseason logs for downstream
  reporting.
- When full conference and division metadata is provided, the season simulator now
  assembles a 17-game NFL slate with home-and-away divisional series, intra- and
  inter-conference rotations, and a 17th cross-conference game per team. The
  scheduler falls back to the previous round-robin behaviour for partial leagues
  and may introduce extra bye weeks while still keeping every club at 17 games.
- Added a persistent `GameStateStore` service that snapshots rosters, free agents,
  used draft picks, and trade history into the new `FranchiseState` table. The
  season simulator hydrates PlayerParticipation objects from this state, ensures
  participant names/IDs are propagated into game stats, and feeds abridged
  snapshots into narrative prompts as lightweight RAG context. Contract
  operations now invoke the store after each signing or cut so roster and
  free-agent data stay synchronized for downstream systems.
- Introduced a draft-class generator (`/draft/generate-class`) that seeds rookie free agents using weighted position distributions, ensures deterministic output with optional seeds, stamps the new `rookie_year` column, and blocks duplicate class creation per season.
- Added `app/services/contracts.py` plus `/contracts/sign` and `/contracts/cut`
  endpoints that model signing-bonus proration, guarantee allocation, dead-money
  schedules, and cap-space enforcement with accompanying unit + async API tests.
- Extended the contracts router with `/contracts/negotiate`, combining
  deterministic free-agent offer metrics with Grok-4-Fast backed negotiation
  pitches and regression coverage for success, opt-out, and failure scenarios.
- `/games/simulate` now runs the shared `InjuryEngine`, persists generated
  injuries to the `injuries` table, updates `PlayerStamina` fatigue levels, and
  captures those results in `injuries_json` for downstream consumers. The new
  `/health` endpoints expose this data for dashboards and monitoring.

This document should be kept current as new tables, rules, or endpoints are introduced.
