from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas import (
    ContractCutRequest,
    ContractCutResponse,
    ContractRead,
    ContractSignRequest,
    ErrorResponse,
    FreeAgentNegotiationRequest,
    FreeAgentNegotiationResponse,
    FreeAgentNegotiationMetrics,
    FreeAgentNarrative,
)
from app.services.contracts import (
    cut_contract,
    evaluate_free_agent_offer,
    sign_contract,
)
from app.services.state import GameStateStore
from app.services.llm import FreeAgentPitch, OpenRouterClient

router = APIRouter(prefix="/contracts", tags=["contracts"])


@router.post(
    "/sign",
    response_model=ContractRead,
    responses={
        404: {"description": "Player or team not found"},
        422: {"description": "Cap validation failed"},
    },
)
async def sign_contract_endpoint(
    payload: ContractSignRequest, db: AsyncSession = Depends(get_db)
) -> ContractRead:
    state_store = GameStateStore(db)
    contract = await sign_contract(db, payload, state_store=state_store)
    return ContractRead.model_validate(contract)


@router.post(
    "/cut",
    response_model=ContractCutResponse,
    responses={
        404: {"description": "Contract or team not found"},
        422: {"description": "League year outside contract term"},
    },
)
async def cut_contract_endpoint(
    payload: ContractCutRequest, db: AsyncSession = Depends(get_db)
) -> ContractCutResponse:
    state_store = GameStateStore(db)
    result = await cut_contract(db, payload, state_store=state_store)
    return ContractCutResponse(**result)


def get_narrative_client() -> Optional[OpenRouterClient]:
    try:
        return OpenRouterClient()
    except Exception:  # pragma: no cover - safeguard for misconfiguration
        return None


def _serialize_pitch(pitch: FreeAgentPitch) -> FreeAgentNarrative:
    return FreeAgentNarrative(
        summary=pitch.summary,
        team_pitch=pitch.team_pitch,
        player_reaction=pitch.player_reaction,
        next_steps=pitch.next_steps,
    )


@router.post(
    "/negotiate",
    response_model=FreeAgentNegotiationResponse,
    responses={
        503: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def negotiate_free_agent_offer(
    payload: FreeAgentNegotiationRequest,
    narrative_client: Optional[OpenRouterClient] = Depends(get_narrative_client),
) -> FreeAgentNegotiationResponse:
    metrics = evaluate_free_agent_offer(payload)
    metrics_model = FreeAgentNegotiationMetrics(
        apy=metrics.apy,
        guaranteed_percentage=metrics.guaranteed_percentage,
        signing_bonus_proration=metrics.signing_bonus_proration,
        market_delta=metrics.market_delta,
        risk_flags=metrics.risk_flags,
    )
    response = FreeAgentNegotiationResponse(
        team_name=payload.team_name,
        player_name=payload.player_name,
        metrics=metrics_model,
    )

    if not payload.include_narrative:
        return response

    if narrative_client is None or not getattr(narrative_client, "api_key", None):
        raise HTTPException(status_code=503, detail="Narrative service is not configured")

    context = {
        "team_name": payload.team_name,
        "player_name": payload.player_name,
        "player_position": payload.player_position,
        "offer": {
            "years": payload.offer_years,
            "total_value": payload.offer_total_value,
            "signing_bonus": payload.signing_bonus,
            "guarantees": (
                payload.guarantees if payload.guarantees is not None else payload.offer_total_value
            ),
            "incentives": payload.incentives,
        },
        "metrics": metrics_model.model_dump(),
        "market_estimate": payload.player_market_apy,
        "progress_summary": payload.tasks_completed,
        "remaining_tasks": payload.tasks_remaining,
        "use_reasoning": True,
        "reasoning_effort": "medium",
    }

    try:
        pitch = await narrative_client.generate_free_agent_pitch(context)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Narrative service unavailable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    response.narrative = _serialize_pitch(pitch)
    return response
