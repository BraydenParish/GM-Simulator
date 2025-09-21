from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.db import get_db
from app.services.persistence import SaveGameManager, SeasonArchiveManager

router = APIRouter(prefix="/franchise", tags=["franchise"])


@router.post("/save")
async def save_franchise(
    save_name: str,
    description: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Save the current franchise state."""
    
    save_manager = SaveGameManager()
    
    try:
        metadata = await save_manager.save_franchise(db, save_name, description)
        
        return {
            "success": True,
            "save_name": save_name,
            "metadata": {
                "created_at": metadata.created_at.isoformat(),
                "current_season": metadata.current_season,
                "current_week": metadata.current_week,
                "total_games": metadata.total_games,
                "total_players": metadata.total_players,
                "total_teams": metadata.total_teams,
                "description": metadata.description,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save franchise: {str(e)}")


@router.post("/load")
async def load_franchise(
    save_name: str,
    clear_existing: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """Load a franchise state from save file."""
    
    save_manager = SaveGameManager()
    
    try:
        metadata = await save_manager.load_franchise(db, save_name, clear_existing)
        
        return {
            "success": True,
            "loaded_save": save_name,
            "metadata": {
                "created_at": metadata.created_at.isoformat(),
                "current_season": metadata.current_season,
                "current_week": metadata.current_week,
                "total_games": metadata.total_games,
                "total_players": metadata.total_players,
                "total_teams": metadata.total_teams,
                "description": metadata.description,
            }
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Save file not found: {save_name}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load franchise: {str(e)}")


@router.get("/saves")
async def list_saves():
    """List all available save files."""
    
    save_manager = SaveGameManager()
    saves = save_manager.list_saves()
    
    return {
        "total_saves": len(saves),
        "saves": [
            {
                "save_name": save.save_name,
                "created_at": save.created_at.isoformat(),
                "current_season": save.current_season,
                "current_week": save.current_week,
                "total_games": save.total_games,
                "total_players": save.total_players,
                "total_teams": save.total_teams,
                "description": save.description,
            }
            for save in saves
        ]
    }


@router.delete("/saves/{save_name}")
async def delete_save(save_name: str):
    """Delete a save file."""
    
    save_manager = SaveGameManager()
    success = save_manager.delete_save(save_name)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"Save file not found: {save_name}")
    
    return {
        "success": True,
        "deleted_save": save_name,
        "message": "Save file deleted successfully"
    }


@router.post("/archive-season")
async def archive_season(
    season: int,
    keep_current_rosters: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """Archive a completed season."""
    
    archive_manager = SeasonArchiveManager()
    
    try:
        archive_path = await archive_manager.archive_season(db, season, keep_current_rosters)
        
        return {
            "success": True,
            "season": season,
            "archive_path": archive_path,
            "keep_current_rosters": keep_current_rosters,
            "message": f"Season {season} archived successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to archive season: {str(e)}")


@router.post("/new-franchise")
async def create_new_franchise(
    franchise_name: str,
    starting_season: int = 2024,
    db: AsyncSession = Depends(get_db),
):
    """Create a new franchise (resets database to initial state)."""
    
    from app.services.state import GameStateStore
    from app.services.draft import OffseasonManager
    
    try:
        # Reset franchise state
        state_store = GameStateStore(db)
        await state_store.ensure_state()
        
        # Generate initial draft picks
        offseason_manager = OffseasonManager(db)
        draft_picks = await offseason_manager._generate_draft_picks(starting_season)
        
        # Save as initial franchise state
        save_manager = SaveGameManager()
        metadata = await save_manager.save_franchise(
            db, 
            franchise_name, 
            f"New franchise started in {starting_season}"
        )
        
        return {
            "success": True,
            "franchise_name": franchise_name,
            "starting_season": starting_season,
            "initial_save_created": True,
            "draft_picks_generated": len(draft_picks),
            "metadata": {
                "created_at": metadata.created_at.isoformat(),
                "current_season": metadata.current_season,
                "current_week": metadata.current_week,
                "total_teams": metadata.total_teams,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create new franchise: {str(e)}")


@router.get("/status")
async def get_franchise_status(db: AsyncSession = Depends(get_db)):
    """Get current franchise status."""
    
    from app.services.state import GameStateStore
    from sqlalchemy import select, func
    from app.models import Game, Player, Team, DraftPick
    
    try:
        # Get franchise state
        state_store = GameStateStore(db)
        state = await state_store.ensure_state()
        
        # Get some stats
        total_games = await db.scalar(select(func.count(Game.id)))
        total_players = await db.scalar(select(func.count(Player.id)))
        total_teams = await db.scalar(select(func.count(Team.id)))
        available_picks = await db.scalar(select(func.count(DraftPick.id)).where(DraftPick.used == False))
        
        return {
            "current_season": state.current_season,
            "current_week": state.current_week,
            "statistics": {
                "total_games": total_games or 0,
                "total_players": total_players or 0,
                "total_teams": total_teams or 0,
                "available_draft_picks": available_picks or 0,
            },
            "last_updated": state.updated_at.isoformat() if state.updated_at else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get franchise status: {str(e)}")


@router.post("/backup")
async def create_backup(
    backup_name: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Create a backup of the current franchise state."""
    
    from datetime import datetime
    
    if not backup_name:
        backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    save_manager = SaveGameManager()
    
    try:
        metadata = await save_manager.save_franchise(
            db, 
            backup_name, 
            f"Automatic backup created at {datetime.now().isoformat()}"
        )
        
        return {
            "success": True,
            "backup_name": backup_name,
            "created_at": metadata.created_at.isoformat(),
            "message": "Backup created successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create backup: {str(e)}")


@router.post("/restore-backup")
async def restore_backup(
    backup_name: str,
    confirm: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Restore from a backup (requires confirmation)."""
    
    if not confirm:
        raise HTTPException(
            status_code=400, 
            detail="Restoration requires confirmation (set confirm=true)"
        )
    
    save_manager = SaveGameManager()
    
    try:
        metadata = await save_manager.load_franchise(db, backup_name, clear_existing=True)
        
        return {
            "success": True,
            "restored_from": backup_name,
            "metadata": {
                "created_at": metadata.created_at.isoformat(),
                "current_season": metadata.current_season,
                "current_week": metadata.current_week,
            },
            "message": "Backup restored successfully"
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Backup not found: {backup_name}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restore backup: {str(e)}")
