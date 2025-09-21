"""Player development and aging system."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Player, PlayerStamina


@dataclass
class DevelopmentEvent:
    """Represents a change in player attributes."""
    player_id: int
    attribute: str
    old_value: int
    new_value: int
    reason: str  # "development", "aging", "training", "injury_recovery"


class PlayerDevelopmentEngine:
    """Manages player attribute changes over time."""
    
    # Age curves for different position groups
    POSITION_GROUPS = {
        "skill": ["QB", "WR", "TE", "RB", "FB"],
        "line": ["LT", "LG", "C", "RG", "RT", "LE", "DT", "RE"],
        "linebacker": ["LOLB", "MLB", "ROLB"],
        "secondary": ["CB", "FS", "SS"],
        "special": ["K", "P"],
    }
    
    # Prime age ranges by position group
    PRIME_AGES = {
        "skill": (25, 30),
        "line": (26, 32),
        "linebacker": (25, 30),
        "secondary": (24, 29),
        "special": (25, 35),
    }
    
    # Development rates by age
    DEVELOPMENT_RATES = {
        # Young players develop quickly
        21: 0.85, 22: 0.80, 23: 0.75, 24: 0.70,
        # Prime years - slow improvement
        25: 0.40, 26: 0.35, 27: 0.30, 28: 0.25, 29: 0.20, 30: 0.15,
        # Decline begins
        31: 0.05, 32: 0.0, 33: -0.05, 34: -0.10, 35: -0.15,
        # Steep decline
        36: -0.25, 37: -0.35, 38: -0.45, 39: -0.55, 40: -0.65
    }
    
    # Attributes that improve/decline at different rates
    PHYSICAL_ATTRIBUTES = ["spd", "acc", "agi", "str"]
    MENTAL_ATTRIBUTES = ["awr", "ovr"]
    POSITION_SPECIFIC = ["thp", "tha_s", "tha_m", "tha_d", "tup"]  # QB attributes
    
    def __init__(self, seed: Optional[int] = None):
        self.random = random.Random(seed)
    
    async def process_offseason_development(self, session: AsyncSession) -> List[DevelopmentEvent]:
        """Process player development for the entire league during offseason."""
        
        # Get all players
        players_result = await session.execute(select(Player))
        players = list(players_result.scalars())
        
        events = []
        
        for player in players:
            if not player.age:
                continue
            
            player_events = await self._develop_player(player, session)
            events.extend(player_events)
        
        await session.commit()
        return events
    
    async def _develop_player(self, player: Player, session: AsyncSession) -> List[DevelopmentEvent]:
        """Develop a single player based on age, potential, and other factors."""
        
        events = []
        age = player.age or 25
        
        # Get base development rate for age
        base_rate = self.DEVELOPMENT_RATES.get(age, 0.0)
        
        # Modify rate based on potential vs current overall
        if player.pot and player.ovr:
            potential_gap = player.pot - player.ovr
            if potential_gap > 0:
                base_rate += potential_gap * 0.02  # Bonus for unfulfilled potential
        
        # Position-specific aging
        position_group = self._get_position_group(player.pos or "")
        prime_start, prime_end = self.PRIME_AGES.get(position_group, (25, 30))
        
        if age < prime_start:
            base_rate += 0.1  # Young players develop faster
        elif age > prime_end:
            base_rate -= 0.1  # Past prime players decline faster
        
        # Check for injury history affecting development
        injury_penalty = await self._get_injury_penalty(player, session)
        base_rate -= injury_penalty
        
        # Apply development to different attribute categories
        events.extend(self._develop_physical_attributes(player, base_rate))
        events.extend(self._develop_mental_attributes(player, base_rate))
        events.extend(self._develop_position_specific(player, base_rate))
        
        # Update overall rating based on other changes
        self._recalculate_overall(player)
        
        return events
    
    def _develop_physical_attributes(self, player: Player, base_rate: float) -> List[DevelopmentEvent]:
        """Develop physical attributes (speed, acceleration, etc.)."""
        
        events = []
        
        # Physical attributes decline faster with age
        age_penalty = max(0, (player.age or 25) - 28) * 0.05
        physical_rate = base_rate - age_penalty
        
        for attr_name in self.PHYSICAL_ATTRIBUTES:
            current_value = getattr(player, attr_name, None)
            if current_value is None:
                continue
            
            # Determine change
            change = self._calculate_attribute_change(current_value, physical_rate)
            
            if change != 0:
                new_value = max(30, min(99, current_value + change))
                setattr(player, attr_name, new_value)
                
                events.append(DevelopmentEvent(
                    player_id=player.id,
                    attribute=attr_name,
                    old_value=current_value,
                    new_value=new_value,
                    reason="aging" if change < 0 else "development"
                ))
        
        return events
    
    def _develop_mental_attributes(self, player: Player, base_rate: float) -> List[DevelopmentEvent]:
        """Develop mental attributes (awareness, etc.)."""
        
        events = []
        
        # Mental attributes improve with experience, decline slowly
        experience_bonus = min(0.1, max(0, (player.age or 21) - 21) * 0.02)
        mental_rate = base_rate + experience_bonus
        
        # Awareness specifically
        if player.awr is not None:
            change = self._calculate_attribute_change(player.awr, mental_rate)
            
            if change != 0:
                new_value = max(30, min(99, player.awr + change))
                player.awr = new_value
                
                events.append(DevelopmentEvent(
                    player_id=player.id,
                    attribute="awr",
                    old_value=player.awr,
                    new_value=new_value,
                    reason="development" if change > 0 else "aging"
                ))
        
        return events
    
    def _develop_position_specific(self, player: Player, base_rate: float) -> List[DevelopmentEvent]:
        """Develop position-specific attributes."""
        
        events = []
        
        # QB-specific development
        if player.pos == "QB":
            for attr_name in ["thp", "tha_s", "tha_m", "tha_d", "tup"]:
                current_value = getattr(player, attr_name, None)
                if current_value is None:
                    continue
                
                # QB accuracy improves with experience
                if "tha_" in attr_name:
                    experience_bonus = 0.05
                else:
                    experience_bonus = 0.0
                
                change = self._calculate_attribute_change(
                    current_value, 
                    base_rate + experience_bonus
                )
                
                if change != 0:
                    new_value = max(30, min(99, current_value + change))
                    setattr(player, attr_name, new_value)
                    
                    events.append(DevelopmentEvent(
                        player_id=player.id,
                        attribute=attr_name,
                        old_value=current_value,
                        new_value=new_value,
                        reason="development" if change > 0 else "aging"
                    ))
        
        return events
    
    def _calculate_attribute_change(self, current_value: int, rate: float) -> int:
        """Calculate the change in an attribute based on current value and rate."""
        
        # Higher rated players improve slower
        difficulty_modifier = 1.0 - (current_value - 50) / 100.0
        adjusted_rate = rate * difficulty_modifier
        
        # Random element
        if self.random.random() < abs(adjusted_rate):
            return 1 if adjusted_rate > 0 else -1
        
        return 0
    
    def _recalculate_overall(self, player: Player):
        """Recalculate overall rating based on other attributes."""
        
        if not player.pos:
            return
        
        # Simple overall calculation based on key attributes
        key_attrs = []
        
        if player.pos == "QB":
            key_attrs = [player.thp, player.tha_s, player.tha_m, player.tha_d, player.awr]
        elif player.pos in ["RB", "FB"]:
            key_attrs = [player.spd, player.acc, player.agi, player.str]
        elif player.pos in ["WR", "TE"]:
            key_attrs = [player.spd, player.acc, player.agi, player.awr]
        else:
            # Default to physical attributes
            key_attrs = [player.spd, player.acc, player.agi, player.str, player.awr]
        
        # Filter out None values
        key_attrs = [attr for attr in key_attrs if attr is not None]
        
        if key_attrs:
            new_overall = int(sum(key_attrs) / len(key_attrs))
            player.ovr = max(40, min(99, new_overall))
    
    def _get_position_group(self, position: str) -> str:
        """Get the position group for aging curves."""
        
        for group, positions in self.POSITION_GROUPS.items():
            if position in positions:
                return group
        
        return "skill"  # Default
    
    async def _get_injury_penalty(self, player: Player, session: AsyncSession) -> float:
        """Calculate development penalty based on injury history."""
        
        # This could query injury history from the database
        # For now, return a small random penalty
        return self.random.uniform(0.0, 0.05)


class StaminaManager:
    """Manages player stamina and fatigue over time."""
    
    def __init__(self):
        pass
    
    async def update_stamina_after_game(
        self, 
        session: AsyncSession, 
        player_id: int, 
        snaps_played: int,
        game_intensity: float = 1.0
    ):
        """Update player stamina after a game."""
        
        # Get or create stamina record
        stamina_result = await session.execute(
            select(PlayerStamina).where(PlayerStamina.player_id == player_id)
        )
        stamina_record = stamina_result.scalar_one_or_none()
        
        if not stamina_record:
            stamina_record = PlayerStamina(
                player_id=player_id,
                fatigue=0.0
            )
            session.add(stamina_record)
        
        # Calculate fatigue based on snaps
        snap_fatigue = snaps_played * 0.5 * game_intensity
        stamina_record.fatigue = min(100.0, stamina_record.fatigue + snap_fatigue)
        
        await session.commit()
    
    async def weekly_stamina_recovery(self, session: AsyncSession):
        """Process weekly stamina recovery for all players."""
        
        stamina_result = await session.execute(select(PlayerStamina))
        stamina_records = list(stamina_result.scalars())
        
        for record in stamina_records:
            # Players recover stamina each week
            recovery_rate = 20.0  # Base recovery
            
            # Better recovery for younger players
            player_result = await session.execute(
                select(Player).where(Player.id == record.player_id)
            )
            player = player_result.scalar_one_or_none()
            
            if player and player.age:
                if player.age < 25:
                    recovery_rate += 5.0
                elif player.age > 32:
                    recovery_rate -= 5.0
            
            record.fatigue = max(0.0, record.fatigue - recovery_rate)
        
        await session.commit()
    
    async def get_player_fatigue(self, session: AsyncSession, player_id: int) -> float:
        """Get current fatigue level for a player."""
        
        stamina_result = await session.execute(
            select(PlayerStamina).where(PlayerStamina.player_id == player_id)
        )
        stamina_record = stamina_result.scalar_one_or_none()
        
        return stamina_record.fatigue if stamina_record else 0.0


class TrainingCampManager:
    """Manages training camp and preseason development."""
    
    def __init__(self, development_engine: PlayerDevelopmentEngine):
        self.development_engine = development_engine
    
    async def run_training_camp(
        self, 
        session: AsyncSession, 
        team_id: int,
        focus_areas: Optional[List[str]] = None
    ) -> List[DevelopmentEvent]:
        """Run training camp for a team with optional focus areas."""
        
        # Get team players
        players_result = await session.execute(
            select(Player).where(Player.team_id == team_id)
        )
        players = list(players_result.scalars())
        
        events = []
        
        for player in players:
            if not player.age or player.age > 35:
                continue  # Veterans don't improve much in camp
            
            # Young players get more benefit from camp
            camp_bonus = 0.1 if player.age < 25 else 0.05
            
            # Focus area bonuses
            focus_bonus = 0.0
            if focus_areas and player.pos in focus_areas:
                focus_bonus = 0.05
            
            total_bonus = camp_bonus + focus_bonus
            
            # Apply small improvements
            if self.development_engine.random.random() < total_bonus:
                # Improve a random attribute slightly
                attrs_to_improve = ["spd", "acc", "agi", "str", "awr"]
                attr_name = self.development_engine.random.choice(attrs_to_improve)
                
                current_value = getattr(player, attr_name, None)
                if current_value is not None and current_value < 90:
                    new_value = min(99, current_value + 1)
                    setattr(player, attr_name, new_value)
                    
                    events.append(DevelopmentEvent(
                        player_id=player.id,
                        attribute=attr_name,
                        old_value=current_value,
                        new_value=new_value,
                        reason="training"
                    ))
        
        await session.commit()
        return events
