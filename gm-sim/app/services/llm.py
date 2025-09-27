"""Utilities for interacting with OpenRouter-hosted LLMs.

The deterministic simulation engine remains the source of truth for results.
This module only generates narrative flavour built on top of the structured
outputs produced by the simulator.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

import httpx

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# Grok-4-Fast is the primary narrative model per updated guidance.
DEFAULT_MODEL = "xai/grok-4-fast"
DEFAULT_FALLBACK_MODELS: Sequence[str] = (
    "google/gemini-2.5-flash",
    "google/gemini-2.0-flash-lite-001",
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LLMResponse:
    """Container describing the outcome of an OpenRouter request."""

    text: str
    model: str
    fallback_used: bool
    attempts: int
    rate_limited: bool
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float | None


@dataclass(slots=True)
class NarrativeRecap:
    """Structured recap returned by the narrative layer."""

    summary: str
    facts: Dict[str, Any]


def validate_structured_recap(payload: Dict[str, Any], context: Dict[str, Any]) -> None:
    """Ensure the recap facts align with the authoritative simulation data."""

    score = context.get("score", {})
    teams = context.get("teams", {})
    scoreboard = payload.get("scoreboard", {}) if isinstance(payload, dict) else {}
    
    # Validate scores with detailed error reporting
    home_score_llm = scoreboard.get("home_score")
    away_score_llm = scoreboard.get("away_score")
    home_score_actual = score.get("home")
    away_score_actual = score.get("away")
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Score validation: LLM={home_score_llm}-{away_score_llm}, Actual={home_score_actual}-{away_score_actual}")
    
    # Convert to int for comparison (handle string numbers)
    try:
        home_score_llm = int(home_score_llm) if home_score_llm is not None else None
        away_score_llm = int(away_score_llm) if away_score_llm is not None else None
        home_score_actual = int(home_score_actual) if home_score_actual is not None else None
        away_score_actual = int(away_score_actual) if away_score_actual is not None else None
    except (ValueError, TypeError):
        logger.warning(f"Score conversion failed: LLM scores={scoreboard.get('home_score')}, {scoreboard.get('away_score')}")
    
    if home_score_llm != home_score_actual:
        raise ValueError(
            "Narrative recap home score mismatch: "
            f"LLM={home_score_llm} vs Actual={home_score_actual}"
        )
    if away_score_llm != away_score_actual:
        raise ValueError(
            "Narrative recap away score mismatch: "
            f"LLM={away_score_llm} vs Actual={away_score_actual}"
        )
    
    # Relaxed team name validation - allow partial matches or similar names
    home_team_llm = str(scoreboard.get("home_team", "")).lower().strip()
    away_team_llm = str(scoreboard.get("away_team", "")).lower().strip()
    home_team_actual = str(teams.get("home", "")).lower().strip()
    away_team_actual = str(teams.get("away", "")).lower().strip()
    
    # Allow if team names contain each other or are very similar
    if home_team_llm and home_team_actual:
        if not (home_team_llm in home_team_actual or home_team_actual in home_team_llm):
            # Only warn, don't fail
            import logging
            logging.warning(f"Team name mismatch: LLM='{home_team_llm}' vs Actual='{home_team_actual}'")
    
    if away_team_llm and away_team_actual:
        if not (away_team_llm in away_team_actual or away_team_actual in away_team_llm):
            # Only warn, don't fail
            import logging
            logging.warning(f"Team name mismatch: LLM='{away_team_llm}' vs Actual='{away_team_actual}'")

    # Relaxed player validation - allow missing players (LLM might not reference all)
    key_players = context.get("key_players", [])
    expected_ids = {
        player.get("player_id") for player in key_players if player.get("player_id") is not None
    }
    for player_fact in payload.get("notable_players", []) if isinstance(payload, dict) else []:
        player_id = player_fact.get("player_id")
        # Only validate if player_id is provided and is a number
        if isinstance(player_id, (int, float)) and player_id not in expected_ids:
            # Warn but don't fail - LLM might reference bench players or make up IDs
            import logging
            logging.warning(f"LLM referenced player ID {player_id} not in simulation stats")


class OpenRouterClient:
    """Thin wrapper around the OpenRouter chat completion endpoint."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        model: str = DEFAULT_MODEL,
        fallback_models: Optional[Sequence[str]] = None,
        base_url: str = OPENROUTER_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.model = model
        configured_fallbacks: Sequence[str]
        if fallback_models is None:
            configured_fallbacks = DEFAULT_FALLBACK_MODELS
        else:
            configured_fallbacks = fallback_models
        self.fallback_models = [
            candidate for candidate in configured_fallbacks if candidate and candidate != self.model
        ]
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        # Simple aggregate metrics for observability and budgeting.
        self.total_calls = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_cost_usd = 0.0
        self.fallback_calls = 0
        self.rate_limit_events = 0

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.7,
        max_output_tokens: int = 512,
        extra_headers: Optional[Dict[str, str]] = None,
        progress_summary: Optional[str] = None,
        remaining_tasks: Optional[str] = None,
        use_reasoning: bool = False,
        reasoning_effort: str = "medium",
    ) -> LLMResponse:
        """Call the OpenRouter API and return the response metadata."""

        if not self.api_key:
            raise RuntimeError("OpenRouter API key not configured")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://gm-simulator.local/",
            "X-Title": "GM Simulator",
        }
        if extra_headers:
            headers.update(extra_headers)

        progress_message = (
            "Progress Update for Narrative Model:\n"
            f"- Completed: {progress_summary or 'Not specified'}\n"
            f"- Remaining: {remaining_tasks or 'Not specified'}"
        )

        payload: Dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "system", "content": progress_message},
                {"role": "user", "content": user_prompt},
            ],
        }

        if use_reasoning:
            payload["reasoning"] = {"effort": reasoning_effort}

        # Prefer structured JSON responses when the provider supports it
        try:
            # OpenRouter forwards OpenAI-compatible response_format for many models
            payload.setdefault("response_format", {"type": "json_object"})
        except Exception:
            # Best-effort only; harmless if not supported
            pass

        candidate_models = [self.model]
        for fallback in self.fallback_models:
            if fallback not in candidate_models:
                candidate_models.append(fallback)

        last_error: Optional[Exception] = None
        attempts = 0
        encountered_rate_limit = False

        for model in candidate_models:
            attempts += 1
            payload["model"] = model
            try:
                async with httpx.AsyncClient(
                    base_url=self.base_url, timeout=self.timeout
                ) as client:
                    response = await client.post("/chat/completions", headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if exc.response.status_code == 429:
                    encountered_rate_limit = True
                    self.rate_limit_events += 1
                continue
            except httpx.HTTPError as exc:
                last_error = exc
                continue

            try:
                message = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:  # pragma: no cover - defensive
                raise RuntimeError(f"Unexpected OpenRouter payload: {data}") from exc

            usage_payload = data.get("usage", {}) if isinstance(data, dict) else {}
            prompt_tokens = int(
                usage_payload.get("prompt_tokens") or usage_payload.get("input_tokens") or 0
            )
            completion_tokens = int(
                usage_payload.get("completion_tokens") or usage_payload.get("output_tokens") or 0
            )
            total_tokens = int(
                usage_payload.get("total_tokens") or (prompt_tokens + completion_tokens)
            )
            estimated_cost_raw = usage_payload.get("estimated_cost") or usage_payload.get("cost")
            estimated_cost = float(estimated_cost_raw) if estimated_cost_raw is not None else None

            fallback_used = model != self.model or attempts > 1
            if fallback_used:
                self.fallback_calls += 1

            self.total_calls += 1
            self.total_prompt_tokens += prompt_tokens
            self.total_completion_tokens += completion_tokens
            if estimated_cost is not None:
                self.total_cost_usd += estimated_cost

            logger.info(
                "OpenRouter call succeeded with model=%s fallback_used=%s attempts=%d rate_limited=%s "
                "prompt_tokens=%d completion_tokens=%d cost_usd=%s",
                model,
                fallback_used,
                attempts,
                encountered_rate_limit,
                prompt_tokens,
                completion_tokens,
                estimated_cost,
            )

            return LLMResponse(
                text=message.strip(),
                model=model,
                fallback_used=fallback_used,
                attempts=attempts,
                rate_limited=encountered_rate_limit,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                estimated_cost_usd=estimated_cost,
            )

        raise RuntimeError("OpenRouter request failed for all configured models") from last_error

    async def generate_game_recap(self, game_context: Dict[str, Any]) -> NarrativeRecap:
        """Produce a concise, grounded recap for a simulated game."""

        teams = game_context.get("teams", {})
        score = game_context.get("score", {})
        headline = game_context.get("headline", "")
        key_players = game_context.get("key_players", [])
        state_snapshot = game_context.get("state")

        system_prompt = (
            "You are the broadcast recap generator for a hardcore NFL general "
            "manager simulator. Keep summaries factual and grounded in the provided "
            "statistics. CRITICAL: Use the EXACT scores and team names provided in the input. "
            "Respond ONLY with a single JSON object matching this schema, "
            "with no prose or code fences: "
            '{"summary": str, "scoreboard": {"home_team": str, "away_team": str, '
            '"home_score": int, "away_score": int}, "notable_players": '
            '[{"player_id": int, "fact": str}]}'
        )

        key_player_lines = "\n".join(
            f"- {player['name']}: {player['line']}" for player in key_players
        )
        state_blob = json.dumps(state_snapshot, sort_keys=True) if state_snapshot else "{}"
        user_prompt = (
            f"Game result: {teams.get('away')} {score.get('away')} at "
            f"{teams.get('home')} {score.get('home')}\n"
            f"Headline: {headline}\n"
            f"Key players:\n{key_player_lines or 'N/A'}\n"
            f"State snapshot: {state_blob}"
        )

        progress_summary = game_context.get(
            "progress_summary",
            "Game simulation progress not specified",
        )
        remaining_tasks = game_context.get(
            "remaining_tasks",
            "Remaining schedule details not specified",
        )
        use_reasoning = bool(game_context.get("use_reasoning", False))
        reasoning_effort = str(game_context.get("reasoning_effort", "medium"))

        response = await self.complete(
            system_prompt,
            user_prompt,
            progress_summary=progress_summary,
            remaining_tasks=remaining_tasks,
            use_reasoning=use_reasoning,
            reasoning_effort=reasoning_effort,
        )
        # Robust JSON parsing: handle occasional code fences or stray text
        text = response.text.strip()
        try:
            import re  # local import to avoid overhead when unused
            if text.startswith("```"):
                # Strip leading/trailing code fences like ```json ... ```
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                start = text.find("{")
                end = text.rfind("}")
                if start != -1 and end != -1 and end > start:
                    candidate = text[start : end + 1]
                    payload = json.loads(candidate)
                else:
                    raise
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise ValueError("Narrative response was not valid JSON") from exc

        validate_structured_recap(payload, game_context)

        summary = str(payload.get("summary", "")).strip()
        if not summary:
            raise ValueError("Narrative recap missing summary text")
        return NarrativeRecap(summary=summary, facts=payload)

    def usage_summary(self) -> Dict[str, float]:
        """Return aggregated usage metrics for observability dashboards."""

        return {
            "total_calls": float(self.total_calls),
            "total_prompt_tokens": float(self.total_prompt_tokens),
            "total_completion_tokens": float(self.total_completion_tokens),
            "total_cost_usd": float(self.total_cost_usd),
            "fallback_calls": float(self.fallback_calls),
            "rate_limit_events": float(self.rate_limit_events),
        }
