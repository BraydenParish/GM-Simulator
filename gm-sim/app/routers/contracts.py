from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas import (
    ContractCutRequest,
    ContractCutResponse,
    ContractRead,
    ContractSignRequest,
)
from app.services.contracts import cut_contract, sign_contract

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
    contract = await sign_contract(db, payload)
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
    result = await cut_contract(db, payload)
    return ContractCutResponse(**result)
