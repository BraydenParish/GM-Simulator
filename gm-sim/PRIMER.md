# PRIMER

## What
- Repointed the `OpenRouterClient` to Grok-4-Fast with layered fallbacks to
  Gemini 2.5 Flash and Gemini 2.0 Flash Lite, plus prompt scaffolding that keeps
  the model aware of completed work and remaining schedule tasks.
- Added coverage for the new reasoning + progress prompt fields alongside the
  existing narrative payload validation tests.
- (Previously) Added the ratings blending pipeline and season simulator
  scaffolding.
- Implemented roster-rule enforcement via `/roster/practice-squad/assign` and
  `/roster/gameday/set-actives`, including 53-man roster totals, the 48/47
  offensive-line rule, practice-squad slot accounting, and elevation caps.
- Delivered cap-aware `/contracts/sign` and `/contracts/cut` endpoints backed by
  a new contract finance service that computes proration, dead-money schedules,
  and cap-space adjustments with regression tests.
- Layered in an injury and fatigue engine with persistence-ready tables and
  season-simulator integration, plus tests that validate league-level incidence
  ranges and fatigue-driven availability penalties.
- Added a persistent `FranchiseState` store + `GameStateStore` helper that
  snapshots rosters/free agents/draft picks, hydrates season simulations with
  real player identities, and feeds abridged RAG context plus fact validation
  into the OpenRouter narrative pipeline.

## Why
- Grok-4-Fast is now the default free narrative provider; fallbacks ensure
  flavour text is still produced whenever Grok is throttled and the progress
  summary keeps long-running simulation context intact.
- Retained documentation of the ratings blend and season simulator context for
  continuity.
- Practice-squad and gameday validation endpoints bring the API closer to NFL
  roster rules and guard against invalid submissions ahead of future sim work.
- Contract operations now mirror core cap mechanics (bonus proration, pre- vs
  post-June-1 releases) so roster churn respects financial constraints.
- Injury modelling gives the sim attrition and load-management hooks ahead of
  future morale and chemistry systems.
- Persistent state snapshots keep trades/free-agent moves grounded across
  seasons and allow narrative outputs to be validated against authoritative
  rosters and box scores.

## Proof
- `pytest -q`
- `pytest tests/api/test_contracts.py -q`
- `pytest tests/services/test_contract_financials.py -q`
- `pytest tests/services/test_injury_engine.py -q`
- `pytest tests/services/test_state_store.py -q`
- `pytest tests/services/test_narrative_grounding.py -q`
- `ruff check .`
- `black --check .`
- `mypy app`
