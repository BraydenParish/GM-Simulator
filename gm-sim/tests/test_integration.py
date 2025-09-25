"""Integration tests for the GM Simulator."""

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.db import get_db
from app.models import Team, Player, DraftPick


class TestGameSimulation:
    """Test game simulation flow."""
    
    @pytest.mark.anyio
    async def test_full_game_simulation(self, async_client: AsyncClient):
        """Test complete game simulation with narrative."""
        
        # First create teams if they don't exist
        response = await async_client.get("/teams/")
        teams = response.json()
        
        if len(teams) < 2:
            # Create test teams
            team1_data = {
                "name": "Test Team 1",
                "abbr": "TT1",
                "conference": "NFC",
                "division": "North"
            }
            team2_data = {
                "name": "Test Team 2", 
                "abbr": "TT2",
                "conference": "AFC",
                "division": "North"
            }
            
            await async_client.post("/teams/", json=team1_data)
            await async_client.post("/teams/", json=team2_data)
            
            # Get updated teams list
            response = await async_client.get("/teams/")
            teams = response.json()
        
        team1_id = teams[0]["id"]
        team2_id = teams[1]["id"]
        
        # Simulate game
        response = await async_client.post(
            "/games/simulate",
            params={
                "home_team_id": team1_id,
                "away_team_id": team2_id,
                "season": 2024,
                "week": 1,
                "generate_narrative": False  # Skip narrative for faster testing
            }
        )
        
        assert response.status_code == 200
        game_data = response.json()
        
        assert game_data["season"] == 2024
        assert game_data["week"] == 1
        assert game_data["home_team_id"] == team1_id
        assert game_data["away_team_id"] == team2_id
        assert "home_score" in game_data
        assert "away_score" in game_data


class TestSeasonOrchestration:
    """Test season management features."""
    
    @pytest.mark.anyio
    async def test_schedule_generation(self, async_client: AsyncClient):
        """Test schedule generation."""
        
        response = await async_client.post(
            "/seasons/generate-schedule",
            params={"season": 2024, "weeks": 3}
        )
        
        assert response.status_code == 200
        schedule_data = response.json()
        
        assert schedule_data["season"] == 2024
        assert schedule_data["weeks_scheduled"] >= 1
        assert schedule_data["total_games"] > 0
    
    @pytest.mark.anyio
    async def test_get_schedule(self, async_client: AsyncClient):
        """Test retrieving schedule."""
        
        response = await async_client.get(
            "/seasons/schedule",
            params={"season": 2024}
        )
        
        assert response.status_code == 200
        schedule_data = response.json()
        
        assert schedule_data["season"] == 2024
        assert "games" in schedule_data


class TestDraftSystem:
    """Test draft functionality."""
    
    @pytest.mark.anyio
    async def test_generate_rookie_class(self, async_client: AsyncClient):
        """Test rookie class generation."""
        
        response = await async_client.post(
            "/draft/generate-rookies",
            params={"year": 2024, "size": 50}
        )
        
        assert response.status_code == 200
        rookies_data = response.json()
        
        assert rookies_data["year"] == 2024
        assert rookies_data["class_size"] == 50
        assert len(rookies_data["rookies"]) > 0
        
        # Check rookie structure
        rookie = rookies_data["rookies"][0]
        assert "name" in rookie
        assert "position" in rookie
        assert "overall" in rookie
        assert "potential" in rookie
    
    @pytest.mark.anyio
    async def test_draft_board(self, async_client: AsyncClient):
        """Test draft board generation."""
        
        response = await async_client.get(
            "/draft/board",
            params={"year": 2024, "limit": 20}
        )
        
        assert response.status_code == 200
        board_data = response.json()
        
        assert board_data["year"] == 2024
        assert len(board_data["prospects"]) <= 20
        
        # Check prospects are ranked
        if len(board_data["prospects"]) > 1:
            assert board_data["prospects"][0]["rank"] == 1
            assert board_data["prospects"][1]["rank"] == 2


class TestTradeSystem:
    """Test trade evaluation and AI."""
    
    @pytest.mark.anyio
    async def test_team_needs_assessment(self, async_client: AsyncClient):
        """Test team needs evaluation."""
        
        # Get first team
        response = await async_client.get("/teams/")
        teams = response.json()
        
        if teams:
            team_id = teams[0]["id"]
            
            response = await async_client.get(f"/trades/team-needs/{team_id}")
            
            assert response.status_code == 200
            needs_data = response.json()
            
            assert needs_data["team_id"] == team_id
            assert "needs" in needs_data
            assert "all_needs" in needs_data
    
    @pytest.mark.anyio
    async def test_legacy_trade_evaluation(self, async_client: AsyncClient):
        """Test legacy trade evaluation."""
        
        response = await async_client.get(
            "/trades/legacy/evaluate",
            params={"team_a_picks": [1, 33], "team_b_picks": [10, 25]}
        )
        
        assert response.status_code == 200
        trade_data = response.json()
        
        assert "team_a_value" in trade_data
        assert "team_b_value" in trade_data
        assert "delta" in trade_data
        assert "winner" in trade_data


class TestDevelopmentSystem:
    """Test player development and injury system."""
    
    @pytest.mark.anyio
    async def test_fatigue_report(self, async_client: AsyncClient):
        """Test fatigue reporting."""
        
        response = await async_client.get(
            "/development/fatigue-report",
            params={"threshold": 0.0}  # Get all players
        )
        
        assert response.status_code == 200
        fatigue_data = response.json()
        
        assert "high_fatigue_players" in fatigue_data
        assert "players" in fatigue_data
    
    @pytest.mark.anyio
    async def test_injury_report(self, async_client: AsyncClient):
        """Test injury reporting."""
        
        response = await async_client.get(
            "/development/injury-report",
            params={"active_only": False, "limit": 10}
        )
        
        assert response.status_code == 200
        injury_data = response.json()
        
        assert "total_injuries" in injury_data
        assert "injuries" in injury_data


class TestFranchiseManagement:
    """Test franchise save/load system."""
    
    @pytest.mark.anyio
    async def test_franchise_status(self, async_client: AsyncClient):
        """Test getting franchise status."""
        
        response = await async_client.get("/franchise/status")
        
        assert response.status_code == 200
        status_data = response.json()
        
        assert "current_season" in status_data
        assert "current_week" in status_data
        assert "statistics" in status_data
    
    @pytest.mark.anyio
    async def test_list_saves(self, async_client: AsyncClient):
        """Test listing save files."""
        
        response = await async_client.get("/franchise/saves")
        
        assert response.status_code == 200
        saves_data = response.json()
        
        assert "total_saves" in saves_data
        assert "saves" in saves_data
    
    @pytest.mark.anyio
    async def test_create_backup(self, async_client: AsyncClient):
        """Test backup creation."""
        
        response = await async_client.post(
            "/franchise/backup",
            params={"backup_name": "test_backup"}
        )
        
        assert response.status_code == 200
        backup_data = response.json()
        
        assert backup_data["success"] is True
        assert backup_data["backup_name"] == "test_backup"


class TestAPIEndpoints:
    """Test basic API functionality."""
    
    @pytest.mark.anyio
    async def test_health_check(self, async_client: AsyncClient):
        """Test health endpoint."""
        
        response = await async_client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    
    @pytest.mark.anyio
    async def test_teams_crud(self, async_client: AsyncClient):
        """Test basic teams CRUD operations."""
        
        # List teams
        response = await async_client.get("/teams/")
        assert response.status_code == 200
        
        # Create team with unique abbreviation
        import random
        unique_abbr = f"T{random.randint(1000, 9999)}"
        
        team_data = {
            "name": "Integration Test Team",
            "abbr": unique_abbr,
            "conference": "NFC",
            "division": "Test"
        }
        
        response = await async_client.post("/teams/", json=team_data)
        assert response.status_code == 200
        
        created_team = response.json()
        team_id = created_team["id"]
        
        # Get specific team
        response = await async_client.get(f"/teams/{team_id}")
        assert response.status_code == 200
        
        team = response.json()
        assert team["name"] == team_data["name"]
        assert team["abbr"] == team_data["abbr"]
        
        # Test duplicate abbreviation returns 409
        duplicate_team_data = {
            "name": "Duplicate Team",
            "abbr": unique_abbr,  # Same abbreviation
            "conference": "AFC",
            "division": "Test"
        }
        
        response = await async_client.post("/teams/", json=duplicate_team_data)
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]
    
    @pytest.mark.anyio
    async def test_players_list(self, async_client: AsyncClient):
        """Test players listing."""
        
        response = await async_client.get("/players/")
        assert response.status_code == 200
        
        players_data = response.json()
        assert "items" in players_data
        assert "total" in players_data
        assert "page" in players_data


@pytest.fixture
async def async_client():
    """Create async test client."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
