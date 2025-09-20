from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db import get_db
from app.models import Transaction
from app.schemas import TransactionRead, TransactionCreate
from typing import List, Dict
from app.services.trades import evaluate_trade

router = APIRouter(prefix="/transactions", tags=["transactions"])

@router.post("/", response_model=TransactionRead)
async def record_transaction(tx_in: TransactionCreate, db: AsyncSession = Depends(get_db)):
    tx = Transaction(**tx_in.model_dump())
    db.add(tx)
    await db.commit()
    await db.refresh(tx)
    return tx

@router.post("/evaluate-trade")
async def evaluate_trade_endpoint(payload: Dict[str, List[int]]):
    # expects {"team_a": [pick_overalls], "team_b": [pick_overalls]}
    return evaluate_trade(payload.get("team_a", []), payload.get("team_b", []))
