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
from typing import Any, Dict, List, Optional, Sequence

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


@dataclass(slots=True)
class TradeDialogue:
    """Structured trade narrative returned by the narrative layer."""

    summary: str
    team_positions: Dict[str, str]
    negotiation_points: List[str]


@dataclass(slots=True)
class FreeAgentPitch:
    """Structured free-agent negotiation payload from the narrative layer."""

    summary: str
    team_pitch: str
    player_reaction: str
    next_steps: List[str]


def validate_structured_recap(payload: Dict[str, Any], context: Dict[str, Any]) -> None:
    """Ensure the recap facts align with the authoritative simulation data."""

    score = context.get("score", {})
    teams = context.get("teams", {})
    scoreboard = payload.get("scoreboard", {}) if isinstance(payload, dict) else {}
    if scoreboard.get("home_score") != score.get("home"):
        raise ValueError("Narrative recap home score does not match simulation output")
    if scoreboard.get("away_score") != score.get("away"):
        raise ValueError("Narrative recap away score does not match simulation output")
    if scoreboard.get("home_team") != teams.get("home"):
        raise ValueError("Narrative recap home team name mismatch")
    if scoreboard.get("away_team") != teams.get("away"):
        raise ValueError("Narrative recap away team name mismatch")

    key_players = context.get("key_players", [])
    expected_ids = {
        player.get("player_id") for player in key_players if player.get("player_id") is not None
    }
    for player_fact in payload.get("notable_players", []) if isinstance(payload, dict) else []:
        player_id = player_fact.get("player_id")
        if player_id not in expected_ids:
            raise ValueError("Narrative recap referenced a player not present in simulation stats")


def validate_trade_dialogue(payload: Dict[str, Any]) -> TradeDialogue:
    """Ensure the trade narrative contains the expected structure."""

    if not isinstance(payload, dict):
        raise ValueError("Narrative trade response must be a JSON object")

    summary = payload.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("Narrative trade response missing summary")

    team_positions = payload.get("team_positions")
    if not isinstance(team_positions, dict):
        raise ValueError("Narrative trade response missing team positions map")

    required_keys = {"team_a", "team_b"}
    missing_keys = required_keys.difference(team_positions.keys())
    if missing_keys:
        raise ValueError("Narrative trade response missing positions for both teams")

    normalised_positions: Dict[str, str] = {}
    for key in required_keys:
        position_text = team_positions.get(key)
        if not isinstance(position_text, str) or not position_text.strip():
            raise ValueError("Narrative trade response contains empty team position text")
        normalised_positions[key] = position_text.strip()

    negotiation_points_raw = payload.get("negotiation_points", [])
    if not isinstance(negotiation_points_raw, list):
        raise ValueError("Narrative trade response negotiation points must be a list")

    negotiation_points: List[str] = []
    for point in negotiation_points_raw:
        if not isinstance(point, str):
            raise ValueError("Narrative trade response negotiation points must be strings")
        trimmed = point.strip()
        if trimmed:
            negotiation_points.append(trimmed)

    if not negotiation_points:
        raise ValueError("Narrative trade response must include at least one negotiation point")

    return TradeDialogue(
        summary=summary.strip(),
        team_positions=normalised_positions,
        negotiation_points=negotiation_points,
    )


def validate_free_agent_pitch(payload: Dict[str, Any]) -> FreeAgentPitch:
    if not isinstance(payload, dict):
        raise ValueError("Narrative free-agent response must be a JSON object")

    summary = payload.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("Narrative free-agent response missing summary")

    team_pitch = payload.get("team_pitch")
    if not isinstance(team_pitch, str) or not team_pitch.strip():
        raise ValueError("Narrative free-agent response missing team pitch text")

    player_reaction = payload.get("player_reaction")
    if not isinstance(player_reaction, str) or not player_reaction.strip():
        raise ValueError("Narrative free-agent response missing player reaction text")

    steps_raw = payload.get("next_steps", [])
    if not isinstance(steps_raw, list):
        raise ValueError("Narrative free-agent response next steps must be a list")

    next_steps: List[str] = []
    for step in steps_raw:
        if not isinstance(step, str):
            raise ValueError("Narrative free-agent response next steps must be strings")
        trimmed = step.strip()
        if trimmed:
            next_steps.append(trimmed)

    if not next_steps:
        raise ValueError("Narrative free-agent response must include at least one next step")

    return FreeAgentPitch(
        summary=summary.strip(),
        team_pitch=team_pitch.strip(),
        player_reaction=player_reaction.strip(),
        next_steps=next_steps,
    )


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
            "manager simulator. Keep summaries factual, grounded in the "
            "provided statistics, and respond with JSON matching the schema: "
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
        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise ValueError("Narrative response was not valid JSON") from exc

        validate_structured_recap(payload, game_context)

        summary = str(payload.get("summary", "")).strip()
        if not summary:
            raise ValueError("Narrative recap missing summary text")
        return NarrativeRecap(summary=summary, facts=payload)

    async def generate_trade_dialogue(self, trade_context: Dict[str, Any]) -> TradeDialogue:
        """Produce a negotiation summary for a proposed trade."""

        teams = trade_context.get("teams", {}) if isinstance(trade_context, dict) else {}
        team_a = teams.get("team_a", {}) if isinstance(teams, dict) else {}
        team_b = teams.get("team_b", {}) if isinstance(teams, dict) else {}
        team_a_name = str(team_a.get("name", "Team A"))
        team_b_name = str(team_b.get("name", "Team B"))
        team_a_assets = team_a.get("assets", []) if isinstance(team_a, dict) else []
        team_b_assets = team_b.get("assets", []) if isinstance(team_b, dict) else []

        evaluation = trade_context.get("evaluation", {}) if isinstance(trade_context, dict) else {}
        team_a_value = int(evaluation.get("team_a_value", 0))
        team_b_value = int(evaluation.get("team_b_value", 0))
        delta = int(evaluation.get("delta", team_a_value - team_b_value))

        focus = trade_context.get("narrative_focus")

        system_prompt = (
            "You are the negotiation analyst for an NFL general manager simulator. "
            "Provide a grounded summary of the proposed trade as JSON with the "
            'structure {"summary": str, "team_positions": {"team_a": str, "team_b": str}, '
            '"negotiation_points": [str, ...]}'
        )

        def _format_assets(assets: Sequence[Any]) -> str:
            return ", ".join(str(asset) for asset in assets) if assets else "None"

        user_prompt_lines = [
            f"Trade proposal between {team_a_name} and {team_b_name}.",
            f"{team_a_name} offers assets: {_format_assets(team_a_assets)} (value {team_a_value}).",
            f"{team_b_name} offers assets: {_format_assets(team_b_assets)} (value {team_b_value}).",
            f"Value delta (Team A - Team B): {delta}.",
        ]
        if focus:
            user_prompt_lines.append(f"Negotiation focus: {focus}")

        user_prompt = "\n".join(user_prompt_lines)

        progress_summary = trade_context.get(
            "progress_summary",
            f"Draft value comparison prepared for {team_a_name} vs {team_b_name}.",
        )
        remaining_tasks = trade_context.get(
            "remaining_tasks",
            "Decide on accept/counter/decline and update cap tables and rosters accordingly.",
        )

        use_reasoning = bool(trade_context.get("use_reasoning", False))
        reasoning_effort = str(trade_context.get("reasoning_effort", "medium"))

        response = await self.complete(
            system_prompt,
            user_prompt,
            progress_summary=progress_summary,
            remaining_tasks=remaining_tasks,
            use_reasoning=use_reasoning,
            reasoning_effort=reasoning_effort,
        )

        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise ValueError("Narrative trade response was not valid JSON") from exc

        return validate_trade_dialogue(payload)

    async def generate_free_agent_pitch(
        self, negotiation_context: Dict[str, Any]
    ) -> FreeAgentPitch:
        """Produce a narrative summary for a free-agent offer."""

        team_name = str(negotiation_context.get("team_name", "Team"))
        player_name = str(negotiation_context.get("player_name", "Player"))
        position = str(negotiation_context.get("player_position", ""))
        offer = (
            negotiation_context.get("offer", {}) if isinstance(negotiation_context, dict) else {}
        )
        metrics = (
            negotiation_context.get("metrics", {}) if isinstance(negotiation_context, dict) else {}
        )

        system_prompt = (
            "You are the contract advisor for an NFL general manager simulator. "
            "Respond with grounded guidance as JSON using the structure "
            '{"summary": str, "team_pitch": str, "player_reaction": str, "next_steps": [str, ...]}. '
            "Do not invent financial figures that contradict the provided context."
        )

        offer_years = offer.get("years")
        offer_total = offer.get("total_value")
        signing_bonus = offer.get("signing_bonus")
        guarantees = offer.get("guarantees")
        incentives = offer.get("incentives", []) if isinstance(offer, dict) else []

        incentives_line = ", ".join(incentives) if incentives else "None"
        market_delta = metrics.get("market_delta")
        risk_flags = metrics.get("risk_flags", []) if isinstance(metrics, dict) else []

        apy_value = metrics.get("apy")
        guaranteed_pct = metrics.get("guaranteed_percentage")
        proration_value = metrics.get("signing_bonus_proration")

        apy_display = f"${apy_value:,.2f}" if isinstance(apy_value, (int, float)) else "N/A"
        guaranteed_display = (
            f"{guaranteed_pct * 100:.1f}%" if isinstance(guaranteed_pct, (int, float)) else "N/A"
        )
        proration_display = (
            f"${proration_value:,.2f}" if isinstance(proration_value, (int, float)) else "N/A"
        )

        total_display = (
            f"${offer_total:,}" if isinstance(offer_total, (int, float)) else str(offer_total)
        )
        signing_bonus_display = (
            f"${signing_bonus:,}" if isinstance(signing_bonus, (int, float)) else str(signing_bonus)
        )
        guarantees_display = (
            f"${guarantees:,}" if isinstance(guarantees, (int, float)) else str(guarantees)
        )

        user_prompt_lines = [
            f"Team: {team_name}",
            f"Player: {player_name} ({position})",
            f"Offer details: {offer_years} years, total {total_display} with signing bonus {signing_bonus_display} and guarantees {guarantees_display}.",
            f"Incentives: {incentives_line}",
            f"Derived metrics: APY {apy_display} | guaranteed % {guaranteed_display} | signing bonus proration {proration_display}.",
        ]

        if isinstance(market_delta, (int, float)):
            user_prompt_lines.append(f"Market delta (offer minus estimate): ${market_delta:,.2f}")
        if risk_flags:
            user_prompt_lines.append("Risk flags: " + "; ".join(str(flag) for flag in risk_flags))

        user_prompt = "\n".join(user_prompt_lines)

        progress_summary = negotiation_context.get(
            "progress_summary",
            f"Initial offer drafted for {player_name} by {team_name}.",
        )
        remaining_tasks = negotiation_context.get(
            "remaining_tasks",
            "Gather agent feedback and adjust cap sheet accordingly.",
        )

        use_reasoning = bool(negotiation_context.get("use_reasoning", False))
        reasoning_effort = str(negotiation_context.get("reasoning_effort", "medium"))

        response = await self.complete(
            system_prompt,
            user_prompt,
            progress_summary=progress_summary,
            remaining_tasks=remaining_tasks,
            use_reasoning=use_reasoning,
            reasoning_effort=reasoning_effort,
        )

        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive safeguard
            raise ValueError("Narrative free-agent response was not valid JSON") from exc

        return validate_free_agent_pitch(payload)

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
