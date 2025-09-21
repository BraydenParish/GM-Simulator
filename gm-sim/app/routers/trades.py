from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional

from app.db import get_db
from app.models import Player, DraftPick, Team, Transaction
from app.services.trade_ai import TradeEvaluator, TradeAI, TradeAsset, TradeAssetType, TradeProposal
from app.services.trades import evaluate_trade, jj_value

router = APIRouter(prefix="/trades", tags=["trades"])


@router.get("/evaluate-player/{player_id}")
async def evaluate_player_trade_value(
    player_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get the trade value for a specific player."""
    
    evaluator = TradeEvaluator(db)
    value = await evaluator.evaluate_player_value(player_id)
    
    player = await db.get(Player, player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    return {
        "player_id": player_id,
        "name": player.name,
        "position": player.pos,
        "overall": player.ovr,
        "age": player.age,
        "trade_value": value,
        "value_tier": (
            "Elite" if value > 1000 else
            "High" if value > 700 else
            "Medium" if value > 400 else
            "Low"
        )
    }


@router.get("/evaluate-pick/{pick_id}")
async def evaluate_pick_trade_value(
    pick_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get the trade value for a specific draft pick."""
    
    evaluator = TradeEvaluator(db)
    value = await evaluator.evaluate_draft_pick_value(pick_id)
    
    pick = await db.get(DraftPick, pick_id)
    if not pick:
        raise HTTPException(status_code=404, detail="Draft pick not found")
    
    return {
        "pick_id": pick_id,
        "year": pick.year,
        "round": pick.round,
        "overall": pick.overall,
        "owned_by_team_id": pick.owned_by_team_id,
        "trade_value": value,
        "jimmy_johnson_value": jj_value(pick.overall or 999),
    }


@router.get("/team-needs/{team_id}")
async def get_team_needs(
    team_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Assess a team's positional needs."""
    
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    evaluator = TradeEvaluator(db)
    needs = await evaluator.assess_team_needs(team_id)
    
    # Sort by need level
    sorted_needs = sorted(needs.items(), key=lambda x: x[1], reverse=True)
    
    return {
        "team_id": team_id,
        "team_name": team.name,
        "needs": {
            "critical": [(pos, need) for pos, need in sorted_needs if need > 0.7],
            "high": [(pos, need) for pos, need in sorted_needs if 0.5 < need <= 0.7],
            "moderate": [(pos, need) for pos, need in sorted_needs if 0.3 < need <= 0.5],
            "low": [(pos, need) for pos, need in sorted_needs if need <= 0.3],
        },
        "all_needs": dict(sorted_needs),
    }


@router.post("/generate-offers/{team_id}")
async def generate_trade_offers(
    team_id: int,
    max_offers: int = 5,
    db: AsyncSession = Depends(get_db),
):
    """Generate AI trade offers for a team based on their needs."""
    
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    evaluator = TradeEvaluator(db)
    trade_ai = TradeAI(db, evaluator)
    
    offers = await trade_ai.generate_trade_offers(team_id, max_offers)
    
    return {
        "team_id": team_id,
        "team_name": team.name,
        "offers_generated": len(offers),
        "offers": [
            {
                "to_team_id": offer.to_team_id,
                "value_delta": offer.value_delta,
                "fairness_score": offer.fairness_score,
                "ai_acceptance_probability": offer.ai_acceptance_probability,
                "offering": [
                    {
                        "type": asset.type.value,
                        "id": asset.id,
                        "value": asset.value,
                        "metadata": asset.metadata,
                    }
                    for asset in offer.from_assets
                ],
                "receiving": [
                    {
                        "type": asset.type.value,
                        "id": asset.id,
                        "value": asset.value,
                        "metadata": asset.metadata,
                    }
                    for asset in offer.to_assets
                ],
            }
            for offer in offers
        ]
    }


@router.post("/evaluate-proposal")
async def evaluate_trade_proposal(
    from_team_id: int,
    to_team_id: int,
    from_player_ids: List[int] = [],
    from_pick_ids: List[int] = [],
    to_player_ids: List[int] = [],
    to_pick_ids: List[int] = [],
    db: AsyncSession = Depends(get_db),
):
    """Evaluate a custom trade proposal."""
    
    evaluator = TradeEvaluator(db)
    
    # Build assets
    from_assets = []
    to_assets = []
    
    # Add players to from_assets
    for player_id in from_player_ids:
        player = await db.get(Player, player_id)
        if player:
            value = await evaluator.evaluate_player_value(player_id)
            from_assets.append(TradeAsset(
                type=TradeAssetType.PLAYER,
                id=player_id,
                value=value,
                metadata={
                    "position": player.pos,
                    "name": player.name,
                    "overall": player.ovr,
                }
            ))
    
    # Add picks to from_assets
    for pick_id in from_pick_ids:
        pick = await db.get(DraftPick, pick_id)
        if pick:
            value = await evaluator.evaluate_draft_pick_value(pick_id)
            from_assets.append(TradeAsset(
                type=TradeAssetType.DRAFT_PICK,
                id=pick_id,
                value=value,
                metadata={
                    "year": pick.year,
                    "round": pick.round,
                    "overall": pick.overall,
                }
            ))
    
    # Add players to to_assets
    for player_id in to_player_ids:
        player = await db.get(Player, player_id)
        if player:
            value = await evaluator.evaluate_player_value(player_id)
            to_assets.append(TradeAsset(
                type=TradeAssetType.PLAYER,
                id=player_id,
                value=value,
                metadata={
                    "position": player.pos,
                    "name": player.name,
                    "overall": player.ovr,
                }
            ))
    
    # Add picks to to_assets
    for pick_id in to_pick_ids:
        pick = await db.get(DraftPick, pick_id)
        if pick:
            value = await evaluator.evaluate_draft_pick_value(pick_id)
            to_assets.append(TradeAsset(
                type=TradeAssetType.DRAFT_PICK,
                id=pick_id,
                value=value,
                metadata={
                    "year": pick.year,
                    "round": pick.round,
                    "overall": pick.overall,
                }
            ))
    
    # Create and evaluate proposal
    proposal = TradeProposal(
        from_team_id=from_team_id,
        to_team_id=to_team_id,
        from_assets=from_assets,
        to_assets=to_assets,
        value_delta=0.0,
        fairness_score=0.0,
        ai_acceptance_probability=0.0,
    )
    
    evaluated_proposal = await evaluator.evaluate_trade_proposal(proposal)
    
    return {
        "from_team_id": from_team_id,
        "to_team_id": to_team_id,
        "evaluation": {
            "value_delta": evaluated_proposal.value_delta,
            "fairness_score": evaluated_proposal.fairness_score,
            "ai_acceptance_probability": evaluated_proposal.ai_acceptance_probability,
            "recommendation": (
                "Excellent trade" if evaluated_proposal.fairness_score > 0.8 else
                "Good trade" if evaluated_proposal.fairness_score > 0.6 else
                "Fair trade" if evaluated_proposal.fairness_score > 0.4 else
                "Poor trade"
            ),
        },
        "from_team_total_value": sum(asset.value for asset in from_assets),
        "to_team_total_value": sum(asset.value for asset in to_assets),
        "from_assets": [
            {
                "type": asset.type.value,
                "id": asset.id,
                "value": asset.value,
                "metadata": asset.metadata,
            }
            for asset in from_assets
        ],
        "to_assets": [
            {
                "type": asset.type.value,
                "id": asset.id,
                "value": asset.value,
                "metadata": asset.metadata,
            }
            for asset in to_assets
        ],
    }


@router.post("/deadline-simulation")
async def simulate_trade_deadline(
    db: AsyncSession = Depends(get_db),
):
    """Simulate AI trades at the trade deadline."""
    
    evaluator = TradeEvaluator(db)
    trade_ai = TradeAI(db, evaluator)
    
    completed_trades = await trade_ai.process_trade_deadline()
    
    # Create transaction records for completed trades
    for trade in completed_trades:
        transaction = Transaction(
            type="trade",
            team_from=trade.from_team_id,
            team_to=trade.to_team_id,
            payload_json={
                "from_assets": [
                    {"type": asset.type.value, "id": asset.id, "metadata": asset.metadata}
                    for asset in trade.from_assets
                ],
                "to_assets": [
                    {"type": asset.type.value, "id": asset.id, "metadata": asset.metadata}
                    for asset in trade.to_assets
                ],
                "value_delta": trade.value_delta,
                "fairness_score": trade.fairness_score,
            }
        )
        db.add(transaction)
    
    await db.commit()
    
    return {
        "trades_completed": len(completed_trades),
        "total_players_moved": sum(
            len([a for a in trade.from_assets + trade.to_assets if a.type == TradeAssetType.PLAYER])
            for trade in completed_trades
        ),
        "total_picks_moved": sum(
            len([a for a in trade.from_assets + trade.to_assets if a.type == TradeAssetType.DRAFT_PICK])
            for trade in completed_trades
        ),
        "trades": [
            {
                "from_team_id": trade.from_team_id,
                "to_team_id": trade.to_team_id,
                "value_delta": trade.value_delta,
                "fairness_score": trade.fairness_score,
                "assets_exchanged": len(trade.from_assets) + len(trade.to_assets),
            }
            for trade in completed_trades
        ]
    }


@router.get("/legacy/evaluate")
async def legacy_evaluate_trade(
    team_a_picks: List[int] = Query(..., description="Overall pick numbers for team A"),
    team_b_picks: List[int] = Query(..., description="Overall pick numbers for team B"),
):
    """Legacy trade evaluation using Jimmy Johnson values only."""
    
    result = evaluate_trade(team_a_picks, team_b_picks)
    
    return {
        "team_a_value": result["team_a"],
        "team_b_value": result["team_b"],
        "delta": result["delta"],
        "winner": "Team A" if result["delta"] > 0 else "Team B" if result["delta"] < 0 else "Even",
        "fairness": "Fair" if abs(result["delta"]) < 100 else "Unfair",
    }
