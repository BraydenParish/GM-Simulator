# PRIMER

## What
- Hardened the `OpenRouterClient` by defaulting to Gemini 2.5 Flash with a
  configurable Gemini 2.0 Flash Lite fallback and richer error handling.
- Added coverage for the retry behaviour alongside the existing narrative
  payload validation tests.
- (Previously) Added the ratings blending pipeline and season simulator
  scaffolding.

## Why
- Narrative generation now degrades gracefully when OpenRouter temporarily
  rejects Gemini 2.5 Flash requests, keeping story output available for recap
  and negotiation flows.
- Retained documentation of the ratings blend and season simulator context for
  continuity.

## Proof
- `pytest -q`
- `ruff check .`
- `black --check .`
- `mypy app`
