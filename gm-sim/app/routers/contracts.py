from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.db import get_db
from app.models import Contract
from app.schemas import ContractRead, ContractCreate
from typing import List

router = APIRouter(prefix="/contracts", tags=["contracts"])

@router.post("/", response_model=ContractRead)
async def create_contract(contract_in: ContractCreate, db: AsyncSession = Depends(get_db)):
    contract = Contract(**contract_in.model_dump())
    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    return contract

@router.post("/{contract_id}/extend", response_model=ContractRead)
async def extend_contract(contract_id: int, years: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    contract.years += years
    await db.commit()
    await db.refresh(contract)
    return contract

@router.delete("/{contract_id}")
async def terminate_contract(contract_id: int, db: AsyncSession = Depends(get_db)):
    await db.execute(delete(Contract).where(Contract.id == contract_id))
    await db.commit()
    return {"ok": True}
