from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Transaction
from app.schemas import (
    ErrorResponse,
    TradeEvaluationRequest,
    TradeEvaluationResponse,
    TradeNarrative,
    TransactionCreate,
    TransactionRead,
)
from app.services.llm import OpenRouterClient, TradeDialogue
from app.services.trades import evaluate_trade

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("/", response_model=TransactionRead)
async def record_transaction(tx_in: TransactionCreate, db: AsyncSession = Depends(get_db)):
    tx = Transaction(**tx_in.model_dump())
    db.add(tx)
    await db.commit()
    await db.refresh(tx)
    return tx


def get_narrative_client() -> Optional[OpenRouterClient]:
    """Instantiate the OpenRouter client for dependency injection."""

    try:
        return OpenRouterClient()
    except Exception:  # pragma: no cover - defensive safeguard for misconfiguration
        return None


def _serialize_dialogue(dialogue: TradeDialogue) -> TradeNarrative:
    return TradeNarrative(
        summary=dialogue.summary,
        team_positions=dialogue.team_positions,
        negotiation_points=dialogue.negotiation_points,
    )


@router.post(
    "/evaluate-trade",
    response_model=TradeEvaluationResponse,
    responses={
        503: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def evaluate_trade_endpoint(
    payload: TradeEvaluationRequest,
    narrative_client: Optional[OpenRouterClient] = Depends(get_narrative_client),
):
    values = evaluate_trade(payload.team_a_assets, payload.team_b_assets)
    response = TradeEvaluationResponse(
        team_a_value=values["team_a"],
        team_b_value=values["team_b"],
        delta=values["delta"],
    )

    if not payload.include_narrative:
        return response

    if narrative_client is None or not getattr(narrative_client, "api_key", None):
        raise HTTPException(status_code=503, detail="Narrative service is not configured")

    context = {
        "teams": {
            "team_a": {"name": payload.team_a_name, "assets": payload.team_a_assets},
            "team_b": {"name": payload.team_b_name, "assets": payload.team_b_assets},
        },
        "evaluation": {
            "team_a_value": response.team_a_value,
            "team_b_value": response.team_b_value,
            "delta": response.delta,
        },
        "narrative_focus": payload.narrative_focus,
        "progress_summary": payload.tasks_completed,
        "remaining_tasks": payload.tasks_remaining,
        "use_reasoning": True,
        "reasoning_effort": "medium",
    }

    try:
        dialogue = await narrative_client.generate_trade_dialogue(context)
    except RuntimeError as exc:  # e.g., failed API call
        raise HTTPException(status_code=503, detail="Narrative service unavailable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    response.narrative = _serialize_dialogue(dialogue)
    return response
