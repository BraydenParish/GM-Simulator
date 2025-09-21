"""Enhanced trade evaluation and AI negotiation system."""

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from enum import Enum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Player, DraftPick, Team, Contract
from app.services.trades import jj_value


class TradeAssetType(Enum):
    PLAYER = "player"
    DRAFT_PICK = "draft_pick"
    CASH = "cash"


@dataclass
class TradeAsset:
    """Represents an asset that can be traded."""
    type: TradeAssetType
    id: int  # player_id, pick_id, or amount for cash
    value: float  # Calculated trade value
    metadata: Dict = None  # Additional info (position, contract, etc.)


@dataclass
class TradeProposal:
    """Represents a complete trade proposal."""
    from_team_id: int
    to_team_id: int
    from_assets: List[TradeAsset]
    to_assets: List[TradeAsset]
    value_delta: float  # Positive means from_team gets more value
    fairness_score: float  # 0-1, higher is more fair
    ai_acceptance_probability: float  # 0-1 chance AI accepts


class TradeEvaluator:
    """Advanced trade evaluation with AI team needs assessment."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def evaluate_player_value(self, player_id: int) -> float:
        """Calculate trade value for a player."""
        
        player = await self.session.get(Player, player_id)
        if not player:
            return 0.0
        
        base_value = (player.ovr or 50) * 10  # Base on overall rating
        
        # Age adjustments
        age = player.age or 25
        if age < 25:
            age_multiplier = 1.2  # Young players more valuable
        elif age < 30:
            age_multiplier = 1.0  # Prime years
        elif age < 33:
            age_multiplier = 0.8  # Declining
        else:
            age_multiplier = 0.5  # Old
        
        base_value *= age_multiplier
        
        # Position adjustments
        position_multipliers = {
            "QB": 1.5, "LT": 1.3, "EDGE": 1.2, "CB": 1.1,
            "WR": 1.0, "RB": 0.9, "TE": 0.9,
            "K": 0.3, "P": 0.3
        }
        
        pos_multiplier = position_multipliers.get(player.pos, 1.0)
        base_value *= pos_multiplier
        
        # Contract considerations
        contract_result = await self.session.execute(
            select(Contract).where(Contract.player_id == player_id, Contract.active == True)
        )
        contract = contract_result.scalar_one_or_none()
        
        if contract:
            # Expensive contracts reduce trade value
            if contract.total_value and contract.total_value > 20_000_000:
                base_value *= 0.8
            elif contract.total_value and contract.total_value > 50_000_000:
                base_value *= 0.6
        
        return max(50, base_value)  # Minimum value
    
    async def evaluate_draft_pick_value(self, pick_id: int) -> float:
        """Calculate trade value for a draft pick."""
        
        pick = await self.session.get(DraftPick, pick_id)
        if not pick or pick.used:
            return 0.0
        
        # Base on Jimmy Johnson value
        base_value = jj_value(pick.overall or 999)
        
        # Adjust for draft year (future picks less valuable)
        current_year = 2024  # Could be dynamic
        year_diff = (pick.year or current_year) - current_year
        
        if year_diff > 0:
            # Future picks discounted
            discount = 0.9 ** year_diff
            base_value *= discount
        
        return base_value
    
    async def assess_team_needs(self, team_id: int) -> Dict[str, float]:
        """Assess team needs by position (0-1 scale, higher = more need)."""
        
        # Get team roster
        roster_result = await self.session.execute(
            select(Player).where(Player.team_id == team_id)
        )
        roster = list(roster_result.scalars())
        
        # Count players by position
        position_counts = {}
        position_quality = {}
        
        for player in roster:
            pos = player.pos or "UNKNOWN"
            position_counts[pos] = position_counts.get(pos, 0) + 1
            
            # Track average quality at position
            if pos not in position_quality:
                position_quality[pos] = []
            position_quality[pos].append(player.ovr or 50)
        
        # Calculate needs based on depth and quality
        needs = {}
        target_counts = {
            "QB": 3, "RB": 4, "WR": 6, "TE": 3,
            "LT": 2, "LG": 2, "C": 2, "RG": 2, "RT": 2,
            "LE": 2, "DT": 4, "RE": 2,
            "LOLB": 2, "MLB": 3, "ROLB": 2,
            "CB": 5, "FS": 2, "SS": 2,
            "K": 1, "P": 1
        }
        
        for pos, target in target_counts.items():
            current_count = position_counts.get(pos, 0)
            avg_quality = sum(position_quality.get(pos, [40])) / len(position_quality.get(pos, [40]))
            
            # Need based on depth shortage
            depth_need = max(0, (target - current_count) / target)
            
            # Need based on quality shortage
            quality_need = max(0, (70 - avg_quality) / 30)
            
            # Combined need (weighted toward depth)
            needs[pos] = depth_need * 0.7 + quality_need * 0.3
        
        return needs
    
    async def evaluate_trade_proposal(self, proposal: TradeProposal) -> TradeProposal:
        """Evaluate a trade proposal and calculate fairness/acceptance probability."""
        
        # Calculate total values
        from_total = sum(asset.value for asset in proposal.from_assets)
        to_total = sum(asset.value for asset in proposal.to_assets)
        
        proposal.value_delta = from_total - to_total
        
        # Calculate fairness (how close to even the trade is)
        if from_total + to_total == 0:
            proposal.fairness_score = 0.0
        else:
            proposal.fairness_score = 1.0 - abs(proposal.value_delta) / (from_total + to_total)
        
        # Assess team needs for acceptance probability
        from_needs = await self.assess_team_needs(proposal.from_team_id)
        to_needs = await self.assess_team_needs(proposal.to_team_id)
        
        # Calculate how well trade addresses needs
        to_need_improvement = 0.0
        
        # Assets TO team gets (helps their needs)
        for asset in proposal.from_assets:
            if asset.type == TradeAssetType.PLAYER and asset.metadata:
                position = asset.metadata.get("position")
                if position in to_needs:
                    to_need_improvement += to_needs[position] * 0.3
        
        # AI acceptance probability for TO team
        base_acceptance = proposal.fairness_score * 0.6  # Fair trades more likely
        need_bonus = min(0.3, to_need_improvement)  # Need fulfillment bonus
        value_penalty = max(0, -proposal.value_delta / 1000) * 0.1  # Penalty for bad value
        
        proposal.ai_acceptance_probability = max(0.05, min(0.95, 
            base_acceptance + need_bonus - value_penalty
        ))
        
        return proposal


class TradeAI:
    """AI system for generating and evaluating trades."""
    
    def __init__(self, session: AsyncSession, evaluator: TradeEvaluator):
        self.session = session
        self.evaluator = evaluator
        self.random = random.Random()
    
    async def generate_trade_offers(self, team_id: int, max_offers: int = 5) -> List[TradeProposal]:
        """Generate AI trade offers for a team based on needs."""
        
        # Get team needs
        needs = await self.evaluator.assess_team_needs(team_id)
        
        # Find highest needs
        sorted_needs = sorted(needs.items(), key=lambda x: x[1], reverse=True)
        target_positions = [pos for pos, need in sorted_needs[:3] if need > 0.3]
        
        if not target_positions:
            return []  # Team doesn't need anything
        
        # Get all other teams
        teams_result = await self.session.execute(select(Team).where(Team.id != team_id))
        other_teams = list(teams_result.scalars())
        
        offers = []
        
        for target_team in other_teams[:max_offers]:
            offer = await self._generate_offer_to_team(team_id, target_team.id, target_positions)
            if offer:
                offers.append(offer)
        
        return offers
    
    async def _generate_offer_to_team(
        self, 
        from_team_id: int, 
        to_team_id: int, 
        desired_positions: List[str]
    ) -> Optional[TradeProposal]:
        """Generate a specific trade offer between two teams."""
        
        # Get target team's players at desired positions
        target_players_result = await self.session.execute(
            select(Player).where(
                Player.team_id == to_team_id,
                Player.pos.in_(desired_positions)
            )
        )
        target_players = list(target_players_result.scalars())
        
        if not target_players:
            return None
        
        # Pick a player to target
        target_player = self.random.choice(target_players)
        target_value = await self.evaluator.evaluate_player_value(target_player.id)
        
        # Build assets to offer
        from_assets = await self._build_offer_package(from_team_id, target_value)
        
        if not from_assets:
            return None
        
        # Create proposal
        to_assets = [TradeAsset(
            type=TradeAssetType.PLAYER,
            id=target_player.id,
            value=target_value,
            metadata={
                "position": target_player.pos,
                "name": target_player.name,
                "overall": target_player.ovr,
            }
        )]
        
        proposal = TradeProposal(
            from_team_id=from_team_id,
            to_team_id=to_team_id,
            from_assets=from_assets,
            to_assets=to_assets,
            value_delta=0.0,  # Will be calculated
            fairness_score=0.0,
            ai_acceptance_probability=0.0,
        )
        
        return await self.evaluator.evaluate_trade_proposal(proposal)
    
    async def _build_offer_package(self, team_id: int, target_value: float) -> List[TradeAsset]:
        """Build a package of assets to offer for a target value."""
        
        assets = []
        current_value = 0.0
        
        # Get team's tradeable players (not stars)
        players_result = await self.session.execute(
            select(Player).where(
                Player.team_id == team_id,
                Player.ovr < 85  # Don't trade stars
            )
        )
        tradeable_players = list(players_result.scalars())
        
        # Get team's draft picks
        picks_result = await self.session.execute(
            select(DraftPick).where(
                DraftPick.owned_by_team_id == team_id,
                DraftPick.used == False
            )
        )
        draft_picks = list(picks_result.scalars())
        
        # Try to build package with picks first (easier to trade)
        for pick in draft_picks:
            if current_value >= target_value * 0.9:  # Close enough
                break
            
            pick_value = await self.evaluator.evaluate_draft_pick_value(pick.id)
            if current_value + pick_value <= target_value * 1.2:  # Don't overpay too much
                assets.append(TradeAsset(
                    type=TradeAssetType.DRAFT_PICK,
                    id=pick.id,
                    value=pick_value,
                    metadata={
                        "year": pick.year,
                        "round": pick.round,
                        "overall": pick.overall,
                    }
                ))
                current_value += pick_value
        
        # Add players if needed
        if current_value < target_value * 0.8:
            for player in tradeable_players:
                if current_value >= target_value * 0.9:
                    break
                
                player_value = await self.evaluator.evaluate_player_value(player.id)
                if current_value + player_value <= target_value * 1.3:
                    assets.append(TradeAsset(
                        type=TradeAssetType.PLAYER,
                        id=player.id,
                        value=player_value,
                        metadata={
                            "position": player.pos,
                            "name": player.name,
                            "overall": player.ovr,
                        }
                    ))
                    current_value += player_value
        
        # Only return if we have a reasonable offer
        if current_value >= target_value * 0.7 and current_value <= target_value * 1.5:
            return assets
        
        return []
    
    async def process_trade_deadline(self) -> List[TradeProposal]:
        """Simulate trades at the trade deadline."""
        
        all_teams_result = await self.session.execute(select(Team))
        all_teams = list(all_teams_result.scalars())
        
        completed_trades = []
        
        for team in all_teams:
            # Generate offers for each team
            offers = await self.generate_trade_offers(team.id, 3)
            
            for offer in offers:
                # Check if AI would accept
                if self.random.random() < offer.ai_acceptance_probability:
                    completed_trades.append(offer)
                    
                    # Execute the trade (simplified)
                    await self._execute_trade(offer)
        
        return completed_trades
    
    async def _execute_trade(self, proposal: TradeProposal):
        """Execute a trade by transferring assets."""
        
        # Transfer players
        for asset in proposal.from_assets:
            if asset.type == TradeAssetType.PLAYER:
                player = await self.session.get(Player, asset.id)
                if player:
                    player.team_id = proposal.to_team_id
        
        for asset in proposal.to_assets:
            if asset.type == TradeAssetType.PLAYER:
                player = await self.session.get(Player, asset.id)
                if player:
                    player.team_id = proposal.from_team_id
        
        # Transfer draft picks
        for asset in proposal.from_assets:
            if asset.type == TradeAssetType.DRAFT_PICK:
                pick = await self.session.get(DraftPick, asset.id)
                if pick:
                    pick.owned_by_team_id = proposal.to_team_id
        
        for asset in proposal.to_assets:
            if asset.type == TradeAssetType.DRAFT_PICK:
                pick = await self.session.get(DraftPick, asset.id)
                if pick:
                    pick.owned_by_team_id = proposal.from_team_id
        
        await self.session.commit()
