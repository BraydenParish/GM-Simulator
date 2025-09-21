"""Multi-season persistence and save/load functionality."""

import json
import os
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Team, Player, Contract, DraftPick, Game, Standing, Schedule, 
    Transaction, FranchiseState, Injury, PlayerStamina
)


@dataclass
class SaveGameMetadata:
    """Metadata for a saved game."""
    save_name: str
    created_at: datetime
    current_season: int
    current_week: int
    total_games: int
    total_players: int
    total_teams: int
    description: Optional[str] = None


@dataclass
class FranchiseSaveData:
    """Complete franchise save data."""
    metadata: SaveGameMetadata
    teams: List[Dict[str, Any]]
    players: List[Dict[str, Any]]
    contracts: List[Dict[str, Any]]
    draft_picks: List[Dict[str, Any]]
    games: List[Dict[str, Any]]
    standings: List[Dict[str, Any]]
    schedule: List[Dict[str, Any]]
    transactions: List[Dict[str, Any]]
    injuries: List[Dict[str, Any]]
    stamina: List[Dict[str, Any]]
    franchise_state: Dict[str, Any]


class SaveGameManager:
    """Manages saving and loading franchise states."""
    
    def __init__(self, save_directory: str = "saves"):
        self.save_directory = Path(save_directory)
        self.save_directory.mkdir(exist_ok=True)
    
    async def save_franchise(
        self, 
        session: AsyncSession, 
        save_name: str,
        description: Optional[str] = None
    ) -> SaveGameMetadata:
        """Save the entire franchise state to disk."""
        
        # Get franchise state for metadata
        franchise_result = await session.execute(select(FranchiseState))
        franchise_state = franchise_result.scalar_one_or_none()
        
        current_season = franchise_state.current_season if franchise_state else 2024
        current_week = franchise_state.current_week if franchise_state else 0
        
        # Count totals for metadata
        games_count = len((await session.execute(select(Game))).scalars().all())
        players_count = len((await session.execute(select(Player))).scalars().all())
        teams_count = len((await session.execute(select(Team))).scalars().all())
        
        metadata = SaveGameMetadata(
            save_name=save_name,
            created_at=datetime.now(),
            current_season=current_season,
            current_week=current_week,
            total_games=games_count,
            total_players=players_count,
            total_teams=teams_count,
            description=description,
        )
        
        # Collect all data
        save_data = FranchiseSaveData(
            metadata=metadata,
            teams=await self._export_teams(session),
            players=await self._export_players(session),
            contracts=await self._export_contracts(session),
            draft_picks=await self._export_draft_picks(session),
            games=await self._export_games(session),
            standings=await self._export_standings(session),
            schedule=await self._export_schedule(session),
            transactions=await self._export_transactions(session),
            injuries=await self._export_injuries(session),
            stamina=await self._export_stamina(session),
            franchise_state=await self._export_franchise_state(session),
        )
        
        # Save to file
        save_path = self.save_directory / f"{save_name}.json"
        with open(save_path, 'w') as f:
            json.dump(asdict(save_data), f, indent=2, default=str)
        
        return metadata
    
    async def load_franchise(
        self, 
        session: AsyncSession, 
        save_name: str,
        clear_existing: bool = True
    ) -> SaveGameMetadata:
        """Load a franchise state from disk."""
        
        save_path = self.save_directory / f"{save_name}.json"
        if not save_path.exists():
            raise FileNotFoundError(f"Save file not found: {save_name}")
        
        with open(save_path, 'r') as f:
            save_data_dict = json.load(f)
        
        # Clear existing data if requested
        if clear_existing:
            await self._clear_database(session)
        
        # Load all data
        await self._import_teams(session, save_data_dict['teams'])
        await self._import_players(session, save_data_dict['players'])
        await self._import_contracts(session, save_data_dict['contracts'])
        await self._import_draft_picks(session, save_data_dict['draft_picks'])
        await self._import_games(session, save_data_dict['games'])
        await self._import_standings(session, save_data_dict['standings'])
        await self._import_schedule(session, save_data_dict['schedule'])
        await self._import_transactions(session, save_data_dict['transactions'])
        await self._import_injuries(session, save_data_dict['injuries'])
        await self._import_stamina(session, save_data_dict['stamina'])
        await self._import_franchise_state(session, save_data_dict['franchise_state'])
        
        await session.commit()
        
        # Return metadata
        metadata_dict = save_data_dict['metadata']
        return SaveGameMetadata(
            save_name=metadata_dict['save_name'],
            created_at=datetime.fromisoformat(metadata_dict['created_at']),
            current_season=metadata_dict['current_season'],
            current_week=metadata_dict['current_week'],
            total_games=metadata_dict['total_games'],
            total_players=metadata_dict['total_players'],
            total_teams=metadata_dict['total_teams'],
            description=metadata_dict.get('description'),
        )
    
    def list_saves(self) -> List[SaveGameMetadata]:
        """List all available save files."""
        
        saves = []
        for save_file in self.save_directory.glob("*.json"):
            try:
                with open(save_file, 'r') as f:
                    save_data = json.load(f)
                
                metadata_dict = save_data.get('metadata', {})
                metadata = SaveGameMetadata(
                    save_name=metadata_dict.get('save_name', save_file.stem),
                    created_at=datetime.fromisoformat(metadata_dict.get('created_at', '2024-01-01T00:00:00')),
                    current_season=metadata_dict.get('current_season', 2024),
                    current_week=metadata_dict.get('current_week', 0),
                    total_games=metadata_dict.get('total_games', 0),
                    total_players=metadata_dict.get('total_players', 0),
                    total_teams=metadata_dict.get('total_teams', 0),
                    description=metadata_dict.get('description'),
                )
                saves.append(metadata)
            except (json.JSONDecodeError, KeyError, ValueError):
                # Skip corrupted save files
                continue
        
        return sorted(saves, key=lambda x: x.created_at, reverse=True)
    
    def delete_save(self, save_name: str) -> bool:
        """Delete a save file."""
        save_path = self.save_directory / f"{save_name}.json"
        if save_path.exists():
            save_path.unlink()
            return True
        return False
    
    async def _clear_database(self, session: AsyncSession):
        """Clear all data from the database."""
        
        # Clear in dependency order
        await session.execute(text("DELETE FROM stamina"))
        await session.execute(text("DELETE FROM injuries"))
        await session.execute(text("DELETE FROM transactions"))
        await session.execute(text("DELETE FROM schedule"))
        await session.execute(text("DELETE FROM standings"))
        await session.execute(text("DELETE FROM games"))
        await session.execute(text("DELETE FROM contracts"))
        await session.execute(text("DELETE FROM draft_picks"))
        await session.execute(text("DELETE FROM players"))
        await session.execute(text("DELETE FROM franchise_state"))
        # Keep teams - they're foundational
        
        await session.commit()
    
    # Export methods
    async def _export_teams(self, session: AsyncSession) -> List[Dict[str, Any]]:
        teams = (await session.execute(select(Team))).scalars().all()
        return [
            {
                "id": team.id,
                "name": team.name,
                "abbr": team.abbr,
                "conference": team.conference,
                "division": team.division,
                "elo": team.elo,
                "scheme_off": team.scheme_off,
                "scheme_def": team.scheme_def,
                "cap_space": team.cap_space,
                "cap_year": team.cap_year,
            }
            for team in teams
        ]
    
    async def _export_players(self, session: AsyncSession) -> List[Dict[str, Any]]:
        players = (await session.execute(select(Player))).scalars().all()
        return [
            {
                "id": player.id,
                "name": player.name,
                "pos": player.pos,
                "team_id": player.team_id,
                "age": player.age,
                "height": player.height,
                "weight": player.weight,
                "ovr": player.ovr,
                "pot": player.pot,
                "spd": player.spd,
                "acc": player.acc,
                "agi": player.agi,
                "str": player.str,
                "awr": player.awr,
                "injury_status": player.injury_status,
                "morale": player.morale,
                "stamina": player.stamina,
                "thp": player.thp,
                "tha_s": player.tha_s,
                "tha_m": player.tha_m,
                "tha_d": player.tha_d,
                "tup": player.tup,
            }
            for player in players
        ]
    
    async def _export_contracts(self, session: AsyncSession) -> List[Dict[str, Any]]:
        contracts = (await session.execute(select(Contract))).scalars().all()
        return [
            {
                "id": contract.id,
                "player_id": contract.player_id,
                "team_id": contract.team_id,
                "years": contract.years,
                "total_value": contract.total_value,
                "guaranteed": contract.guaranteed,
                "signing_bonus": contract.signing_bonus,
                "cap_hit_y1": contract.cap_hit_y1,
                "cap_hit_y2": contract.cap_hit_y2,
                "cap_hit_y3": contract.cap_hit_y3,
                "cap_hit_y4": contract.cap_hit_y4,
                "dead_money": contract.dead_money,
                "active": contract.active,
            }
            for contract in contracts
        ]
    
    async def _export_draft_picks(self, session: AsyncSession) -> List[Dict[str, Any]]:
        picks = (await session.execute(select(DraftPick))).scalars().all()
        return [
            {
                "id": pick.id,
                "year": pick.year,
                "round": pick.round,
                "overall": pick.overall,
                "owned_by_team_id": pick.owned_by_team_id,
                "original_team_id": pick.original_team_id,
                "jj_value": pick.jj_value,
                "alt_value": pick.alt_value,
                "used": pick.used,
            }
            for pick in picks
        ]
    
    async def _export_games(self, session: AsyncSession) -> List[Dict[str, Any]]:
        games = (await session.execute(select(Game))).scalars().all()
        return [
            {
                "id": game.id,
                "season": game.season,
                "week": game.week,
                "home_team_id": game.home_team_id,
                "away_team_id": game.away_team_id,
                "home_score": game.home_score,
                "away_score": game.away_score,
                "sim_seed": game.sim_seed,
                "box_json": game.box_json,
                "injuries_json": game.injuries_json,
                "narrative_recap": game.narrative_recap,
                "narrative_facts": game.narrative_facts,
            }
            for game in games
        ]
    
    async def _export_standings(self, session: AsyncSession) -> List[Dict[str, Any]]:
        standings = (await session.execute(select(Standing))).scalars().all()
        return [
            {
                "season": standing.season,
                "team_id": standing.team_id,
                "wins": standing.wins,
                "losses": standing.losses,
                "ties": standing.ties,
                "pf": standing.pf,
                "pa": standing.pa,
                "elo": standing.elo,
            }
            for standing in standings
        ]
    
    async def _export_schedule(self, session: AsyncSession) -> List[Dict[str, Any]]:
        schedule = (await session.execute(select(Schedule))).scalars().all()
        return [
            {
                "id": game.id,
                "season": game.season,
                "week": game.week,
                "home_team_id": game.home_team_id,
                "away_team_id": game.away_team_id,
                "game_time": game.game_time.isoformat() if game.game_time else None,
            }
            for game in schedule
        ]
    
    async def _export_transactions(self, session: AsyncSession) -> List[Dict[str, Any]]:
        transactions = (await session.execute(select(Transaction))).scalars().all()
        return [
            {
                "id": transaction.id,
                "type": transaction.type,
                "team_from": transaction.team_from,
                "team_to": transaction.team_to,
                "payload_json": transaction.payload_json,
                "cap_delta_from": transaction.cap_delta_from,
                "cap_delta_to": transaction.cap_delta_to,
                "timestamp": transaction.timestamp.isoformat() if transaction.timestamp else None,
            }
            for transaction in transactions
        ]
    
    async def _export_injuries(self, session: AsyncSession) -> List[Dict[str, Any]]:
        injuries = (await session.execute(select(Injury))).scalars().all()
        return [
            {
                "id": injury.id,
                "player_id": injury.player_id,
                "team_id": injury.team_id,
                "game_id": injury.game_id,
                "type": injury.type,
                "severity": injury.severity,
                "expected_weeks_out": injury.expected_weeks_out,
                "occurred_at_play_id": injury.occurred_at_play_id,
                "occurred_at": injury.occurred_at.isoformat() if injury.occurred_at else None,
            }
            for injury in injuries
        ]
    
    async def _export_stamina(self, session: AsyncSession) -> List[Dict[str, Any]]:
        stamina_records = (await session.execute(select(PlayerStamina))).scalars().all()
        return [
            {
                "id": record.id,
                "player_id": record.player_id,
                "fatigue": record.fatigue,
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,
            }
            for record in stamina_records
        ]
    
    async def _export_franchise_state(self, session: AsyncSession) -> Dict[str, Any]:
        state = (await session.execute(select(FranchiseState))).scalar_one_or_none()
        if not state:
            return {}
        
        return {
            "id": state.id,
            "current_season": state.current_season,
            "current_week": state.current_week,
            "roster_snapshot": state.roster_snapshot,
            "free_agents": state.free_agents,
            "draft_picks_used": state.draft_picks_used,
            "trades": state.trades,
            "updated_at": state.updated_at.isoformat() if state.updated_at else None,
        }
    
    # Import methods
    async def _import_teams(self, session: AsyncSession, teams_data: List[Dict[str, Any]]):
        for team_data in teams_data:
            team = Team(**{k: v for k, v in team_data.items() if k != 'id'})
            team.id = team_data['id']
            session.add(team)
        await session.flush()
    
    async def _import_players(self, session: AsyncSession, players_data: List[Dict[str, Any]]):
        for player_data in players_data:
            player = Player(**{k: v for k, v in player_data.items() if k != 'id'})
            player.id = player_data['id']
            session.add(player)
        await session.flush()
    
    async def _import_contracts(self, session: AsyncSession, contracts_data: List[Dict[str, Any]]):
        for contract_data in contracts_data:
            contract = Contract(**{k: v for k, v in contract_data.items() if k != 'id'})
            contract.id = contract_data['id']
            session.add(contract)
        await session.flush()
    
    async def _import_draft_picks(self, session: AsyncSession, picks_data: List[Dict[str, Any]]):
        for pick_data in picks_data:
            pick = DraftPick(**{k: v for k, v in pick_data.items() if k != 'id'})
            pick.id = pick_data['id']
            session.add(pick)
        await session.flush()
    
    async def _import_games(self, session: AsyncSession, games_data: List[Dict[str, Any]]):
        for game_data in games_data:
            game = Game(**{k: v for k, v in game_data.items() if k != 'id'})
            game.id = game_data['id']
            session.add(game)
        await session.flush()
    
    async def _import_standings(self, session: AsyncSession, standings_data: List[Dict[str, Any]]):
        for standing_data in standings_data:
            standing = Standing(**standing_data)
            session.add(standing)
        await session.flush()
    
    async def _import_schedule(self, session: AsyncSession, schedule_data: List[Dict[str, Any]]):
        for game_data in schedule_data:
            game_time = None
            if game_data.get('game_time'):
                game_time = datetime.fromisoformat(game_data['game_time'])
            
            game = Schedule(
                id=game_data['id'],
                season=game_data['season'],
                week=game_data['week'],
                home_team_id=game_data['home_team_id'],
                away_team_id=game_data['away_team_id'],
                game_time=game_time,
            )
            session.add(game)
        await session.flush()
    
    async def _import_transactions(self, session: AsyncSession, transactions_data: List[Dict[str, Any]]):
        for transaction_data in transactions_data:
            timestamp = None
            if transaction_data.get('timestamp'):
                timestamp = datetime.fromisoformat(transaction_data['timestamp'])
            
            transaction = Transaction(
                id=transaction_data['id'],
                type=transaction_data['type'],
                team_from=transaction_data['team_from'],
                team_to=transaction_data['team_to'],
                payload_json=transaction_data['payload_json'],
                cap_delta_from=transaction_data['cap_delta_from'],
                cap_delta_to=transaction_data['cap_delta_to'],
                timestamp=timestamp,
            )
            session.add(transaction)
        await session.flush()
    
    async def _import_injuries(self, session: AsyncSession, injuries_data: List[Dict[str, Any]]):
        for injury_data in injuries_data:
            occurred_at = None
            if injury_data.get('occurred_at'):
                occurred_at = datetime.fromisoformat(injury_data['occurred_at'])
            
            injury = Injury(
                id=injury_data['id'],
                player_id=injury_data['player_id'],
                team_id=injury_data['team_id'],
                game_id=injury_data['game_id'],
                type=injury_data['type'],
                severity=injury_data['severity'],
                expected_weeks_out=injury_data['expected_weeks_out'],
                occurred_at_play_id=injury_data['occurred_at_play_id'],
                occurred_at=occurred_at,
            )
            session.add(injury)
        await session.flush()
    
    async def _import_stamina(self, session: AsyncSession, stamina_data: List[Dict[str, Any]]):
        for record_data in stamina_data:
            updated_at = None
            if record_data.get('updated_at'):
                updated_at = datetime.fromisoformat(record_data['updated_at'])
            
            record = PlayerStamina(
                id=record_data['id'],
                player_id=record_data['player_id'],
                fatigue=record_data['fatigue'],
                updated_at=updated_at,
            )
            session.add(record)
        await session.flush()
    
    async def _import_franchise_state(self, session: AsyncSession, state_data: Dict[str, Any]):
        if not state_data:
            return
        
        updated_at = None
        if state_data.get('updated_at'):
            updated_at = datetime.fromisoformat(state_data['updated_at'])
        
        state = FranchiseState(
            id=state_data['id'],
            current_season=state_data['current_season'],
            current_week=state_data['current_week'],
            roster_snapshot=state_data['roster_snapshot'],
            free_agents=state_data['free_agents'],
            draft_picks_used=state_data['draft_picks_used'],
            trades=state_data['trades'],
            updated_at=updated_at,
        )
        session.add(state)
        await session.flush()


class SeasonArchiveManager:
    """Manages archiving completed seasons."""
    
    def __init__(self, archive_directory: str = "archives"):
        self.archive_directory = Path(archive_directory)
        self.archive_directory.mkdir(exist_ok=True)
    
    async def archive_season(
        self, 
        session: AsyncSession, 
        season: int,
        keep_current_rosters: bool = True
    ) -> str:
        """Archive a completed season and optionally clean up data."""
        
        # Export season data
        archive_data = {
            "season": season,
            "archived_at": datetime.now().isoformat(),
            "games": await self._get_season_games(session, season),
            "standings": await self._get_season_standings(session, season),
            "transactions": await self._get_season_transactions(session, season),
            "injuries": await self._get_season_injuries(session, season),
        }
        
        # Save archive
        archive_path = self.archive_directory / f"season_{season}.json"
        with open(archive_path, 'w') as f:
            json.dump(archive_data, f, indent=2, default=str)
        
        # Clean up old data if requested
        if not keep_current_rosters:
            await self._cleanup_season_data(session, season)
        
        return str(archive_path)
    
    async def _get_season_games(self, session: AsyncSession, season: int) -> List[Dict[str, Any]]:
        games = (await session.execute(
            select(Game).where(Game.season == season)
        )).scalars().all()
        
        return [
            {
                "week": game.week,
                "home_team_id": game.home_team_id,
                "away_team_id": game.away_team_id,
                "home_score": game.home_score,
                "away_score": game.away_score,
                "narrative_recap": game.narrative_recap,
            }
            for game in games
        ]
    
    async def _get_season_standings(self, session: AsyncSession, season: int) -> List[Dict[str, Any]]:
        standings = (await session.execute(
            select(Standing).where(Standing.season == season)
        )).scalars().all()
        
        return [
            {
                "team_id": standing.team_id,
                "wins": standing.wins,
                "losses": standing.losses,
                "ties": standing.ties,
                "points_for": standing.pf,
                "points_against": standing.pa,
            }
            for standing in standings
        ]
    
    async def _get_season_transactions(self, session: AsyncSession, season: int) -> List[Dict[str, Any]]:
        # This would need a season field on transactions, or date filtering
        transactions = (await session.execute(select(Transaction))).scalars().all()
        
        return [
            {
                "type": t.type,
                "team_from": t.team_from,
                "team_to": t.team_to,
                "timestamp": t.timestamp.isoformat() if t.timestamp else None,
            }
            for t in transactions
        ]
    
    async def _get_season_injuries(self, session: AsyncSession, season: int) -> List[Dict[str, Any]]:
        # Get injuries from games in this season
        injuries = (await session.execute(
            select(Injury).join(Game).where(Game.season == season)
        )).scalars().all()
        
        return [
            {
                "player_id": injury.player_id,
                "type": injury.type,
                "severity": injury.severity,
                "weeks_out": injury.expected_weeks_out,
            }
            for injury in injuries
        ]
    
    async def _cleanup_season_data(self, session: AsyncSession, season: int):
        """Remove old season data to save space."""
        
        # Delete old games
        await session.execute(text(f"DELETE FROM games WHERE season = {season}"))
        
        # Delete old standings  
        await session.execute(text(f"DELETE FROM standings WHERE season = {season}"))
        
        # Delete old schedule
        await session.execute(text(f"DELETE FROM schedule WHERE season = {season}"))
        
        await session.commit()
