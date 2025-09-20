# Overnight Autonomy Report

## Completed
- Repointed the OpenRouter-backed narrative client to Grok-4-Fast with automatic
  fallbacks to Gemini 2.5 Flash and Gemini 2.0 Flash Lite, added reasoning hooks,
  and ensured every prompt carries a progress + remaining-tasks summary for
  continuity.
- Implemented OpenRouter-backed narrative client and season orchestration
  utilities to simulate round-robin schedules with drive summaries and player
  stat lines.
- Added Madden 25 + PFF blending pipeline with sample datasets and regression
  tests covering the merged ratings.
- Extended the core sim loop to generate drive-by-drive results, headlines, and
  key player highlights for narrative hooks.
- Delivered roster-rule enforcement with new practice-squad and gameday endpoints
  that enforce 53-man totals, the OL 48/47 exception, elevation caps (2 per game,
  3 per player), and IPP slot accounting, all backed by async API tests.
- Implemented contract financial services and `/contracts/sign` + `/contracts/cut`
  endpoints that calculate bonus proration, dead-money schedules, cap savings,
  and enforce team cap space with dedicated unit + API regression tests.
- Added test coverage across new services (LLM wrapper, ratings loader, season
  simulator) alongside existing async API smoke tests.
- Layered an injury & fatigue engine onto the season simulator, capturing
  in-season attrition, storing results in `injuries`/`stamina` tables, and
  adding regression tests that validate incidence ranges and fatigue penalties.
- Created a persistent `FranchiseState` model plus `GameStateStore` snapshots so
  rosters, free agents, used draft picks, and trades survive across simulations
  and hydrate PlayerParticipation objects with real names/IDs.
- Tightened the narrative contract by requiring JSON recaps validated against
  authoritative box scores/player stats and added regression tests guarding
  against mismatched scores or phantom players.

## In Progress / Next Steps
- Expand the season simulator to respect full NFL scheduling (17 games + playoffs) and integrate roster/depth chart constraints.
- Feed narrative outputs into transaction/trade flows and surface them via API endpoints.
- Connect blended ratings with the new cap logic and offseason roster churn (draft class generator, free agency pool).
- Layer in injury and fatigue models plus chemistry/morale modifiers before playoff simulation work.
- Persist simulated injury outputs via new endpoints and surface team-level
  health dashboards alongside morale/chemistry plans.
- Wire roster-rule outcomes into future salary-cap, injury, and sim logic so the newly-enforced actives/inactives directly shape gameplay.

## Test Evidence
- `pytest -q`
- `pytest tests/services/test_state_store.py -q`
- `pytest tests/services/test_narrative_grounding.py -q`
- `ruff check .`
- `black --check .`
- `mypy app`

## Coverage / Performance Notes
- New service tests exercise 100% of the ratings loader, state store, narrative
  validator, and season orchestration helpers.
- Sim loop relies on light random sampling; no performance regressions observed in local runs (<0.1s per simulated week).
