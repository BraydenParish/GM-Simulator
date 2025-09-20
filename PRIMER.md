# PRIMER

## What
- Repointed the `OpenRouterClient` to Grok-4-Fast with layered fallbacks to
  Gemini 2.5 Flash and Gemini 2.0 Flash Lite, plus prompt scaffolding that keeps
  the model aware of completed work and remaining schedule tasks.
- Added coverage for the new reasoning + progress prompt fields alongside the
  existing narrative payload validation tests.
- Introduced trade evaluation narratives that enrich `/transactions/evaluate-trade`
  responses with Grok-backed negotiation summaries whenever requested.
- Added `/contracts/negotiate`, blending deterministic free-agent offer metrics with
  Grok-4-Fast generated negotiation pitches (with opt-out and error handling).
- (Previously) Added the ratings blending pipeline and season simulator
  scaffolding.
- Implemented roster-rule enforcement via `/roster/practice-squad/assign` and
  `/roster/gameday/set-actives`, including 53-man roster totals, the 48/47
  offensive-line rule, practice-squad slot accounting, and elevation caps.
- Delivered cap-aware `/contracts/sign` and `/contracts/cut` endpoints backed by
  a new contract finance service that computes proration, dead-money schedules,
  and cap-space adjustments with regression tests.
- Hooked contract sign/cut flows into the persistent `GameStateStore` so roster
  and free-agent snapshots refresh automatically after cap transactions.
- Layered in an injury and fatigue engine with persistence-ready tables and
  season-simulator integration, plus tests that validate league-level incidence
  ranges and fatigue-driven availability penalties.
- Persisted single-game injury outputs into the database, updating
  `PlayerStamina` fatigue and exposing `/health/injuries` + `/health/summary`
  dashboards for downstream consumers.
- Built a deterministic rookie draft-class generator (`/draft/generate-class`) that writes `rookie_year` metadata, enforces one class per season, and supports custom position weights for future roster planning.
- Added a persistent `FranchiseState` store + `GameStateStore` helper that
  snapshots rosters/free agents/draft picks, hydrates season simulations with
  real player identities, and feeds abridged RAG context plus fact validation
  into the OpenRouter narrative pipeline.
- Expanded the season simulator with NFL-inspired tie-breakers (win %, head-to-head,
  point differential, points for) and a seeded postseason bracket that produces
  conference championships and a Super Bowl game log for downstream narrative use.
- Season scheduling now builds a 17-game NFL slate when conference/division metadata
  is available, covering divisional home-and-home, intra-conference rotations, and
  cross-conference opponents while preserving the round-robin fallback for partial
  leagues.

## Why
- Grok-4-Fast is now the default free narrative provider; fallbacks ensure
  flavour text is still produced whenever Grok is throttled and the progress
  summary keeps long-running simulation context intact.
- Retained documentation of the ratings blend and season simulator context for
  continuity.
- Grounded trade negotiation text in deterministic Jimmy Johnson valuations so
  flavour output mirrors the numeric assessment returned by the API.
- Free-agent negotiations now return cap-relevant metrics (APY, guarantees,
  proration, market delta) plus optional Grok narratives, giving GMs actionable
  data alongside flavour text.
- Practice-squad and gameday validation endpoints bring the API closer to NFL
  roster rules and guard against invalid submissions ahead of future sim work.
- Contract operations now mirror core cap mechanics (bonus proration, pre- vs
  post-June-1 releases) so roster churn respects financial constraints, and the
  state store now refreshes immediately after each signing or cut.
- Injury modelling gives the sim attrition and load-management hooks ahead of
  future morale and chemistry systems.
- Persisted injury/fatigue data plus `/health` endpoints allow dashboards and
  monitoring to pull grounded medical reports rather than relying on in-memory
  simulator artifacts.
- Persistent state snapshots keep trades/free-agent moves grounded across
  seasons and allow narrative outputs to be validated against authoritative
  rosters and box scores.
- Draft-class generation gives offseason pipelines fresh talent pools with realistic positional mixes and deterministic seeds so future free-agency and trade logic can reason about rookie supply.
- League tables now honour realistic tie-breaking rules and postseason structure,
  producing deterministic seeding for playoff simulations and giving the narrative
  layer richer milestones (conference championships, Super Bowl).
- The expanded scheduling logic keeps the sim aligned with 17-game NFL seasons and
  still supports ad-hoc leagues via the existing round-robin fallback.

## Proof
- `pytest -q`
- `pytest tests/api/test_contracts.py -q`
- `pytest tests/api/test_contracts.py::test_negotiate_free_agent_offer_returns_narrative -q`
- `pytest tests/api/test_contracts.py::test_contract_updates_state_store -q`
- `pytest tests/services/test_contract_financials.py -q`
- `pytest tests/services/test_injury_engine.py -q`
- `pytest tests/services/test_state_store.py -q`
- `pytest tests/services/test_narrative_grounding.py -q`
- `pytest tests/services/test_llm.py::test_generate_trade_dialogue_returns_structured_payload -q`
- `pytest tests/services/test_llm.py::test_generate_free_agent_pitch_returns_structured_payload -q`
- `pytest tests/services/test_season_simulator.py::test_head_to_head_tiebreak_prioritises_direct_results -q`
- `pytest tests/services/test_season_simulator.py::test_playoffs_follow_seed_order -q`
- `pytest tests/services/test_season_simulator.py::test_nfl_schedule_generates_seventeen_games -q`
- `pytest tests/api/test_transactions.py -q`
- `pytest tests/api/test_draft.py -q`
- `pytest tests/api/test_games.py -q`
- `pytest tests/api/test_health.py -q`
- `ruff check .`
- `black --check .`
- `mypy app`
