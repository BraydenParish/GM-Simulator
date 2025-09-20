# PRIMER

## What
- Repointed the `OpenRouterClient` to Grok-4-Fast with layered fallbacks to
  Gemini 2.5 Flash and Gemini 2.0 Flash Lite, plus prompt scaffolding that keeps
  the model aware of completed work and remaining schedule tasks.
- Added coverage for the new reasoning + progress prompt fields alongside the
  existing narrative payload validation tests.
- (Previously) Added the ratings blending pipeline and season simulator
  scaffolding.

## Why
- Grok-4-Fast is now the default free narrative provider; fallbacks ensure
  flavour text is still produced whenever Grok is throttled and the progress
  summary keeps long-running simulation context intact.
- Retained documentation of the ratings blend and season simulator context for
  continuity.

## Proof
- `pytest -q`
- `ruff check .`
- `black --check .`
- `mypy app`
