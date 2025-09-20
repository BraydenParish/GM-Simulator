from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas import (
    DraftClassGenerationRequest,
    DraftClassGenerationResponse,
    PlayerRead,
)
from app.services.draft import generate_draft_class

router = APIRouter(prefix="/draft", tags=["draft"])


@router.post(
    "/generate-class",
    response_model=DraftClassGenerationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_draft_class_endpoint(
    payload: DraftClassGenerationRequest,
    db: AsyncSession = Depends(get_db),
) -> DraftClassGenerationResponse:
    players = await generate_draft_class(db, payload)
    return DraftClassGenerationResponse(
        year=payload.year,
        total=len(players),
        items=[PlayerRead.model_validate(player) for player in players],
    )
