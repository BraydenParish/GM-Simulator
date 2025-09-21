"""Draft and rookie generation system."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DraftPick, Player, Team, Contract


@dataclass
class RookieProfile:
    """Generated rookie player profile."""
    name: str
    position: str
    age: int
    height: int
    weight: int
    college: str
    ovr: int
    pot: int
    spd: int
    acc: int
    agi: int
    str: int
    awr: int
    # Position-specific attributes will be generated based on position


class RookieGenerator:
    """Generates realistic rookie prospects for the draft."""
    
    POSITIONS = ["QB", "RB", "FB", "WR", "TE", "LT", "LG", "C", "RG", "RT", 
                 "LE", "DT", "RE", "LOLB", "MLB", "ROLB", "CB", "FS", "SS", "K", "P"]
    
    POSITION_WEIGHTS = {
        "QB": 0.08, "RB": 0.12, "FB": 0.02, "WR": 0.15, "TE": 0.08,
        "LT": 0.06, "LG": 0.06, "C": 0.04, "RG": 0.06, "RT": 0.06,
        "LE": 0.06, "DT": 0.08, "RE": 0.06, "LOLB": 0.06, "MLB": 0.04, "ROLB": 0.06,
        "CB": 0.12, "FS": 0.06, "SS": 0.06, "K": 0.02, "P": 0.02
    }
    
    COLLEGES = [
        "Alabama", "Georgia", "Ohio State", "Clemson", "Oklahoma", "LSU", "Michigan",
        "Texas", "Notre Dame", "Florida", "Penn State", "USC", "Oregon", "Miami",
        "Auburn", "Wisconsin", "Iowa", "Stanford", "Washington", "Virginia Tech",
        "TCU", "Baylor", "Utah", "Arizona State", "Colorado", "Nebraska", "Tennessee"
    ]
    
    FIRST_NAMES = [
        "James", "Michael", "Robert", "John", "David", "William", "Richard", "Joseph",
        "Thomas", "Christopher", "Charles", "Daniel", "Matthew", "Anthony", "Mark",
        "Donald", "Steven", "Paul", "Andrew", "Joshua", "Kenneth", "Kevin", "Brian",
        "George", "Timothy", "Ronald", "Jason", "Edward", "Jeffrey", "Ryan", "Jacob",
        "Gary", "Nicholas", "Eric", "Jonathan", "Stephen", "Larry", "Justin", "Scott",
        "Brandon", "Benjamin", "Samuel", "Gregory", "Alexander", "Patrick", "Frank",
        "Raymond", "Jack", "Dennis", "Jerry", "Tyler", "Aaron", "Jose", "Henry"
    ]
    
    LAST_NAMES = [
        "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
        "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
        "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
        "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
        "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
        "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
        "Carter", "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz", "Parker"
    ]
    
    def __init__(self, seed: Optional[int] = None):
        self.random = random.Random(seed)
    
    def generate_rookie_class(self, year: int, size: int = 256) -> List[RookieProfile]:
        """Generate a full rookie class for the draft."""
        rookies = []
        
        for pick_num in range(1, size + 1):
            # Higher picks get better prospects
            talent_modifier = self._get_talent_modifier(pick_num, size)
            position = self._select_position()
            rookie = self._generate_rookie(position, talent_modifier, year)
            rookies.append(rookie)
        
        return rookies
    
    def _get_talent_modifier(self, pick_num: int, total_picks: int) -> float:
        """Calculate talent modifier based on draft position."""
        # First round gets +10 to +20 modifier
        # Second round gets +5 to +15 modifier  
        # Later rounds get 0 to +10 modifier
        if pick_num <= 32:  # First round
            return self.random.uniform(10, 20)
        elif pick_num <= 64:  # Second round
            return self.random.uniform(5, 15)
        elif pick_num <= 128:  # Rounds 3-4
            return self.random.uniform(2, 10)
        else:  # Late rounds
            return self.random.uniform(0, 5)
    
    def _select_position(self) -> str:
        """Select a position based on realistic draft distribution."""
        return self.random.choices(
            list(self.POSITION_WEIGHTS.keys()),
            weights=list(self.POSITION_WEIGHTS.values()),
            k=1
        )[0]
    
    def _generate_rookie(self, position: str, talent_modifier: float, year: int) -> RookieProfile:
        """Generate a single rookie player."""
        name = f"{self.random.choice(self.FIRST_NAMES)} {self.random.choice(self.LAST_NAMES)}"
        age = self.random.randint(21, 23)
        college = self.random.choice(self.COLLEGES)
        
        # Base physical attributes by position
        height, weight = self._get_physical_attributes(position)
        
        # Base ratings (50-70 range, modified by talent)
        base_ovr = self.random.randint(50, 70) + int(talent_modifier)
        base_ovr = min(99, max(40, base_ovr))  # Clamp to reasonable range
        
        # Potential is usually higher than current overall
        pot = min(99, base_ovr + self.random.randint(0, 15))
        
        # Generate core attributes
        spd = self._generate_attribute(position, "speed", talent_modifier)
        acc = self._generate_attribute(position, "acceleration", talent_modifier)  
        agi = self._generate_attribute(position, "agility", talent_modifier)
        str_attr = self._generate_attribute(position, "strength", talent_modifier)
        awr = self._generate_attribute(position, "awareness", talent_modifier)
        
        return RookieProfile(
            name=name,
            position=position,
            age=age,
            height=height,
            weight=weight,
            college=college,
            ovr=base_ovr,
            pot=pot,
            spd=spd,
            acc=acc,
            agi=agi,
            str=str_attr,
            awr=awr,
        )
    
    def _get_physical_attributes(self, position: str) -> Tuple[int, int]:
        """Get realistic height/weight for position."""
        if position == "QB":
            height = self.random.randint(72, 78)  # 6'0" - 6'6"
            weight = self.random.randint(200, 240)
        elif position in ["RB", "FB"]:
            height = self.random.randint(68, 74)  # 5'8" - 6'2"
            weight = self.random.randint(190, 250)
        elif position in ["WR"]:
            height = self.random.randint(70, 78)  # 5'10" - 6'6"
            weight = self.random.randint(170, 220)
        elif position == "TE":
            height = self.random.randint(74, 80)  # 6'2" - 6'8"
            weight = self.random.randint(240, 280)
        elif position in ["LT", "LG", "C", "RG", "RT"]:  # OL
            height = self.random.randint(74, 80)  # 6'2" - 6'8"
            weight = self.random.randint(290, 340)
        elif position in ["LE", "DT", "RE"]:  # DL
            height = self.random.randint(74, 80)  # 6'2" - 6'8"
            weight = self.random.randint(260, 320)
        elif position in ["LOLB", "MLB", "ROLB"]:  # LB
            height = self.random.randint(72, 78)  # 6'0" - 6'6"
            weight = self.random.randint(230, 270)
        elif position in ["CB", "FS", "SS"]:  # DB
            height = self.random.randint(68, 76)  # 5'8" - 6'4"
            weight = self.random.randint(180, 220)
        else:  # K, P
            height = self.random.randint(70, 76)  # 5'10" - 6'4"
            weight = self.random.randint(180, 220)
        
        return height, weight
    
    def _generate_attribute(self, position: str, attribute: str, talent_modifier: float) -> int:
        """Generate position-appropriate attribute values."""
        base = self.random.randint(45, 75)
        
        # Position-specific boosts
        if attribute == "speed":
            if position in ["WR", "CB", "RB"]:
                base += self.random.randint(5, 15)
        elif attribute == "strength":
            if position in ["LT", "LG", "C", "RG", "RT", "LE", "DT", "RE"]:
                base += self.random.randint(10, 20)
        elif attribute == "agility":
            if position in ["WR", "CB", "RB", "QB"]:
                base += self.random.randint(5, 10)
        elif attribute == "awareness":
            if position in ["QB", "MLB", "C"]:
                base += self.random.randint(5, 15)
        
        # Apply talent modifier
        base += int(talent_modifier * 0.3)  # Moderate influence
        
        return min(99, max(30, base))


class DraftSimulator:
    """Simulates draft selections and manages the draft process."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.generator = RookieGenerator()
    
    async def conduct_draft(self, year: int, auto_draft: bool = True) -> List[Player]:
        """Conduct the full draft for a given year."""
        
        # Get all draft picks for this year, ordered by draft position
        picks_result = await self.session.execute(
            select(DraftPick)
            .where(DraftPick.year == year, DraftPick.used == False)
            .order_by(DraftPick.overall)
        )
        draft_picks = list(picks_result.scalars())
        
        if not draft_picks:
            raise ValueError(f"No available draft picks found for year {year}")
        
        # Generate rookie class
        rookie_class = self.generator.generate_rookie_class(year, len(draft_picks) + 50)
        
        drafted_players = []
        
        for pick in draft_picks:
            if auto_draft:
                # AI selects best available player for team needs
                selected_rookie = await self._ai_select_player(pick, rookie_class, drafted_players)
            else:
                # For manual drafting, just take next best available
                selected_rookie = rookie_class[len(drafted_players)]
            
            # Create player in database
            player = await self._create_drafted_player(selected_rookie, pick)
            drafted_players.append(player)
            
            # Mark pick as used
            pick.used = True
        
        await self.session.commit()
        return drafted_players
    
    async def _ai_select_player(
        self, 
        pick: DraftPick, 
        rookie_class: List[RookieProfile], 
        already_drafted: List[Player]
    ) -> RookieProfile:
        """AI logic for selecting best available player for team needs."""
        
        # Get team roster to assess needs
        team_result = await self.session.execute(
            select(Player).where(Player.team_id == pick.owned_by_team_id)
        )
        team_roster = list(team_result.scalars())
        
        # Count players by position
        position_counts = {}
        for player in team_roster:
            pos = player.pos or "UNKNOWN"
            position_counts[pos] = position_counts.get(pos, 0) + 1
        
        # Available rookies (not yet drafted)
        drafted_names = {p.name for p in already_drafted}
        available_rookies = [r for r in rookie_class if r.name not in drafted_names]
        
        # Score rookies based on talent + team need
        best_rookie = None
        best_score = -1
        
        for rookie in available_rookies[:50]:  # Consider top 50 available
            talent_score = rookie.ovr + rookie.pot * 0.3
            
            # Need multiplier (less players at position = higher need)
            need_multiplier = max(1.0, 5.0 - position_counts.get(rookie.position, 0))
            
            total_score = talent_score * need_multiplier
            
            if total_score > best_score:
                best_score = total_score
                best_rookie = rookie
        
        return best_rookie or available_rookies[0]  # Fallback to first available
    
    async def _create_drafted_player(self, rookie: RookieProfile, pick: DraftPick) -> Player:
        """Create a new player from a rookie profile."""
        
        player = Player(
            name=rookie.name,
            pos=rookie.position,
            team_id=pick.owned_by_team_id,
            age=rookie.age,
            height=rookie.height,
            weight=rookie.weight,
            ovr=rookie.ovr,
            pot=rookie.pot,
            spd=rookie.spd,
            acc=rookie.acc,
            agi=rookie.agi,
            str=rookie.str,
            awr=rookie.awr,
            injury_status="OK",
            morale=75,  # Rookies start with decent morale
            stamina=90,  # Young and fresh
        )
        
        self.session.add(player)
        await self.session.flush()  # Get player ID
        
        # Create rookie contract (4 years, slotted by draft position)
        contract_value = self._calculate_rookie_contract_value(pick.overall)
        contract = Contract(
            player_id=player.id,
            team_id=pick.owned_by_team_id,
            years=4,
            total_value=contract_value,
            guaranteed=int(contract_value * 0.6),  # 60% guaranteed
            signing_bonus=int(contract_value * 0.2),  # 20% signing bonus
            cap_hit_y1=int(contract_value * 0.25),
            cap_hit_y2=int(contract_value * 0.25),
            cap_hit_y3=int(contract_value * 0.25),
            cap_hit_y4=int(contract_value * 0.25),
            dead_money=int(contract_value * 0.4),
            active=True,
        )
        
        self.session.add(contract)
        return player
    
    def _calculate_rookie_contract_value(self, overall_pick: int) -> int:
        """Calculate rookie contract value based on draft position (rookie scale)."""
        if overall_pick <= 10:
            return random.randint(15_000_000, 25_000_000)  # Top 10 picks
        elif overall_pick <= 32:
            return random.randint(8_000_000, 15_000_000)   # Rest of first round
        elif overall_pick <= 64:
            return random.randint(4_000_000, 8_000_000)    # Second round
        elif overall_pick <= 128:
            return random.randint(2_000_000, 4_000_000)    # Rounds 3-4
        else:
            return random.randint(500_000, 2_000_000)      # Late rounds


class OffseasonManager:
    """Manages offseason processes like free agency and contract rollovers."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def advance_to_offseason(self, completed_season: int) -> Dict[str, int]:
        """Process end-of-season activities and advance to offseason."""
        
        results = {
            "contracts_expired": 0,
            "players_released": 0,
            "free_agents_created": 0,
            "draft_picks_generated": 0,
        }
        
        # Expire contracts
        expired_contracts = await self._expire_contracts(completed_season)
        results["contracts_expired"] = len(expired_contracts)
        
        # Age players
        await self._age_players()
        
        # Generate next year's draft picks
        next_season = completed_season + 1
        draft_picks = await self._generate_draft_picks(next_season)
        results["draft_picks_generated"] = len(draft_picks)
        
        await self.session.commit()
        return results
    
    async def _expire_contracts(self, season: int) -> List[Contract]:
        """Expire contracts and create free agents."""
        
        # Get all active contracts
        contracts_result = await self.session.execute(
            select(Contract).where(Contract.active == True)
        )
        active_contracts = list(contracts_result.scalars())
        
        expired_contracts = []
        
        for contract in active_contracts:
            # Simple expiration logic - could be more sophisticated
            if random.random() < 0.15:  # 15% of contracts expire each year
                contract.active = False
                expired_contracts.append(contract)
                
                # Make player a free agent
                player_result = await self.session.execute(
                    select(Player).where(Player.id == contract.player_id)
                )
                player = player_result.scalar_one_or_none()
                if player:
                    player.team_id = None  # Free agent
        
        return expired_contracts
    
    async def _age_players(self):
        """Age all players by one year."""
        
        players_result = await self.session.execute(select(Player))
        players = list(players_result.scalars())
        
        for player in players:
            if player.age:
                player.age += 1
                
                # Slight overall decline for older players
                if player.age > 30 and player.ovr and player.ovr > 60:
                    decline = random.randint(0, 2)
                    player.ovr = max(50, player.ovr - decline)
    
    async def _generate_draft_picks(self, year: int) -> List[DraftPick]:
        """Generate draft picks for the next season."""
        
        # Get all teams
        teams_result = await self.session.execute(select(Team))
        teams = list(teams_result.scalars())
        
        draft_picks = []
        overall_pick = 1
        
        # Generate 7 rounds of picks
        for round_num in range(1, 8):
            for team in teams:
                pick = DraftPick(
                    year=year,
                    round=round_num,
                    overall=overall_pick,
                    owned_by_team_id=team.id,
                    original_team_id=team.id,
                    jj_value=self._calculate_jimmy_johnson_value(overall_pick),
                    used=False,
                )
                
                self.session.add(pick)
                draft_picks.append(pick)
                overall_pick += 1
        
        return draft_picks
    
    def _calculate_jimmy_johnson_value(self, overall_pick: int) -> int:
        """Calculate Jimmy Johnson draft value for a pick."""
        if overall_pick == 1:
            return 3000
        elif overall_pick <= 32:
            # First round values decrease exponentially
            return int(3000 * (0.85 ** (overall_pick - 1)))
        elif overall_pick <= 64:
            # Second round
            return int(500 * (0.95 ** (overall_pick - 33)))
        else:
            # Later rounds
            return max(1, int(100 * (0.98 ** (overall_pick - 65))))
