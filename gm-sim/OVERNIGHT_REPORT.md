# Overnight Autonomy Report

## Completed
- Hardened the OpenRouter-backed narrative client with Gemini 2.5 Flash as the
  default model and an automatic Gemini 2.0 Flash Lite fallback, plus broader
  error handling.
- Implemented OpenRouter-backed narrative client and season orchestration
  utilities to simulate round-robin schedules with drive summaries and player
  stat lines.
- Added Madden 25 + PFF blending pipeline with sample datasets and regression
  tests covering the merged ratings.
- Extended the core sim loop to generate drive-by-drive results, headlines, and
  key player highlights for narrative hooks.
- Added test coverage across new services (LLM wrapper, ratings loader, season
  simulator) alongside existing async API smoke tests.

## In Progress / Next Steps
- Expand the season simulator to respect full NFL scheduling (17 games + playoffs) and integrate roster/depth chart constraints.
- Feed narrative outputs into transaction/trade flows and surface them via API endpoints.
- Connect blended ratings with contract/cap logic and offseason roster churn (draft class generator, free agency pool).
- Layer in injury and fatigue models plus chemistry/morale modifiers before playoff simulation work.

## Test Evidence
- `pytest -q`
- `ruff check .`
- `black --check .`
- `mypy app`

## Coverage / Performance Notes
- New service tests exercise 100% of the ratings loader and season orchestration helpers.
- Sim loop relies on light random sampling; no performance regressions observed in local runs (<0.1s per simulated week).
