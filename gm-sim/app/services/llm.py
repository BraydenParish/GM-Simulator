"""Utilities for interacting with OpenRouter-hosted LLMs.

The deterministic simulation engine remains the source of truth for results.
This module only generates narrative flavour built on top of the structured
outputs produced by the simulator.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# Gemini 2.5 Flash is the default narrative model per product guidance.
DEFAULT_MODEL = "google/gemini-2.5-flash"
DEFAULT_FALLBACK_MODEL = "google/gemini-2.0-flash-lite-001"


class OpenRouterClient:
    """Thin wrapper around the OpenRouter chat completion endpoint."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        model: str = DEFAULT_MODEL,
        fallback_model: Optional[str] = DEFAULT_FALLBACK_MODEL,
        base_url: str = OPENROUTER_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.model = model
        self.fallback_model = fallback_model if fallback_model != model else None
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.7,
        max_output_tokens: int = 512,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> str:
        """Call the OpenRouter API and return the response text.

        Parameters
        ----------
        system_prompt:
            Instruction for the assistant that defines tone and guardrails.
        user_prompt:
            Content supplied by the simulator that describes the event.
        temperature:
            Soft randomness control. Keep relatively low for determinism.
        max_output_tokens:
            Upper bound on generated tokens to bound latency and cost.
        extra_headers:
            Optional headers for experimentation (e.g., provider hints).
        """

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

        payload: Dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        candidate_models = [self.model]
        if self.fallback_model and self.fallback_model not in candidate_models:
            candidate_models.append(self.fallback_model)

        last_error: Optional[Exception] = None
        for model in candidate_models:
            payload["model"] = model
            try:
                async with httpx.AsyncClient(
                    base_url=self.base_url, timeout=self.timeout
                ) as client:
                    response = await client.post("/chat/completions", headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
            except httpx.HTTPError as exc:
                last_error = exc
                continue

            try:
                message = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:  # pragma: no cover - defensive
                raise RuntimeError(f"Unexpected OpenRouter payload: {data}") from exc
            return message.strip()

        raise RuntimeError("OpenRouter request failed for all configured models") from last_error

    async def generate_game_recap(self, game_context: Dict[str, Any]) -> str:
        """Produce a concise recap for a simulated game.

        The context should include metadata such as teams, score, pivotal
        players, and any narrative hooks (injuries, streaks, etc.).
        """

        teams = game_context.get("teams", {})
        score = game_context.get("score", {})
        headline = game_context.get("headline", "")
        key_players = game_context.get("key_players", [])

        system_prompt = (
            "You are the broadcast recap generator for a hardcore NFL general "
            "manager simulator. Keep summaries factual, grounded in the "
            "provided statistics, and limit responses to three paragraphs."
        )

        key_player_lines = "\n".join(
            f"- {player['name']}: {player['line']}" for player in key_players
        )
        user_prompt = (
            f"Game result: {teams.get('away')} {score.get('away')} at "
            f"{teams.get('home')} {score.get('home')}\n"
            f"Headline: {headline}\n"
            f"Key players:\n{key_player_lines or 'N/A'}"
        )

        return await self.complete(system_prompt, user_prompt)
