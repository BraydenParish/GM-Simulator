# GM Simulator API Guide

## Overview

The GM Simulator provides a comprehensive REST API for managing an NFL franchise simulation. This guide covers all major endpoints and workflows.

## Base URL
```
http://localhost:8000
```

## Authentication
Currently no authentication required. All endpoints are publicly accessible.

## Core Concepts

### Teams
- **Endpoint**: `/teams/`
- Teams represent NFL franchises with attributes like name, conference, division, Elo rating, and salary cap space.

### Players  
- **Endpoint**: `/players/`
- Players have comprehensive attributes including ratings, physical stats, contract status, and injury information.

### Contracts
- **Endpoint**: `/contracts/`
- Manage player contracts with salary cap implications, guaranteed money, and dead money calculations.

### Draft Picks
- **Endpoint**: `/draft/`
- Full draft system with rookie generation, pick trading, and Jimmy Johnson value calculations.

## Major Workflows

### 1. Game Simulation

#### Single Game
```http
POST /games/simulate
```

Parameters:
- `home_team_id` (int): ID of home team
- `away_team_id` (int): ID of away team  
- `season` (int): Season year
- `week` (int): Week number
- `generate_narrative` (bool): Whether to generate AI narrative (default: true)

Response includes:
- Game scores
- Box score statistics
- Drive-by-drive results
- AI-generated narrative recap (if enabled)
- Updated standings

#### Full Season Simulation
```http
POST /seasons/simulate-full
```

Parameters:
- `season` (int): Season to simulate
- `generate_narratives` (bool): Generate narratives for games
- `use_injuries` (bool): Enable injury simulation

Simulates an entire season with:
- Round-robin schedule generation
- All games with realistic results
- Updated standings throughout
- Injury tracking and fatigue
- AI-generated storylines

### 2. Draft System

#### Generate Rookie Class
```http
POST /draft/generate-rookies
```

Creates realistic rookie prospects with:
- Position-appropriate physical attributes
- Ratings based on draft position
- College information
- Development potential

#### Conduct Draft
```http
POST /draft/conduct
```

Parameters:
- `year` (int): Draft year
- `auto_draft` (bool): AI handles all picks vs manual

AI draft logic considers:
- Team positional needs
- Best available talent
- Value vs draft position

#### Draft Board
```http
GET /draft/board
```

Get scouted prospects ranked by talent with grades and projections.

### 3. Trade System

#### Evaluate Player Value
```http
GET /trades/evaluate-player/{player_id}
```

Advanced trade value calculation considering:
- Overall rating and potential
- Age and position value
- Contract situation
- Injury history

#### Team Needs Assessment  
```http
GET /trades/team-needs/{team_id}
```

AI analysis of team needs by position based on:
- Roster depth
- Player quality
- Positional importance

#### Generate Trade Offers
```http
POST /trades/generate-offers/{team_id}
```

AI generates realistic trade proposals:
- Targets players at positions of need
- Builds fair value packages
- Considers team salary cap situation
- Calculates acceptance probability

#### Trade Deadline Simulation
```http
POST /trades/deadline-simulation
```

Simulates league-wide trading with AI teams making deals based on needs and value.

### 4. Player Development

#### Process Development
```http
POST /development/process-offseason
```

Ages all players and applies development/decline based on:
- Age curves by position
- Potential vs current rating
- Injury history impact
- Usage and experience

#### Training Camp
```http
POST /development/training-camp
```

Parameters:
- `team_id` (int): Team running camp
- `focus_areas` (list): Positions to emphasize

Young players can improve through focused training.

#### Injury Management
```http
GET /development/injury-report
GET /development/fatigue-report
POST /development/weekly-recovery
```

Comprehensive injury and fatigue system:
- Position-specific injury rates
- Severity and recovery time
- Fatigue accumulation and recovery
- Impact on performance

### 5. Franchise Management

#### Save/Load System
```http
POST /franchise/save
POST /franchise/load  
GET /franchise/saves
DELETE /franchise/saves/{save_name}
```

Full franchise persistence:
- Complete database state
- Season continuity
- Progress tracking
- Multiple save slots

#### Season Archives
```http
POST /franchise/archive-season
```

Archive completed seasons to save space while preserving historical data.

#### Franchise Status
```http
GET /franchise/status
```

Current franchise overview with key statistics.

## Advanced Features

### Narrative AI Integration

The system integrates with OpenRouter LLMs to generate:
- Game recaps with key storylines
- Player performance summaries  
- Season narrative arcs
- Trade and draft analysis

Set `OPENROUTER_API_KEY` environment variable to enable.

### Salary Cap Management

Comprehensive salary cap system:
- Contract structuring with guaranteed money
- Dead money calculations
- Cap space tracking
- Prorated bonuses and restructures

### Roster Rules Enforcement

Automatic enforcement of NFL roster rules:
- 53-man roster limits
- Practice squad management (16 players)
- Gameday actives (48 players, 47 for games)
- Elevation tracking

### Statistics Tracking

Detailed statistics at multiple levels:
- Per-game player stats
- Season aggregates
- Team performance metrics
- Historical comparisons

## Error Handling

The API uses standard HTTP status codes:
- `200` - Success
- `201` - Created
- `400` - Bad Request (validation errors)
- `404` - Not Found
- `422` - Unprocessable Entity (data validation)
- `500` - Internal Server Error

Error responses include descriptive messages:
```json
{
  "detail": "Team not found"
}
```

## Rate Limiting

Currently no rate limiting implemented. For production use, consider implementing rate limiting based on your infrastructure needs.

## OpenAPI Documentation

Interactive API documentation available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Examples

### Complete Season Workflow

1. **Setup New Season**
```bash
# Generate schedule
curl -X POST "http://localhost:8000/seasons/generate-schedule?season=2024&weeks=17"

# Generate draft picks  
curl -X POST "http://localhost:8000/draft/generate-picks?year=2024"
```

2. **Conduct Draft**
```bash
curl -X POST "http://localhost:8000/draft/conduct?year=2024&auto_draft=true"
```

3. **Simulate Season**
```bash
curl -X POST "http://localhost:8000/seasons/simulate-full?season=2024&generate_narratives=true&use_injuries=true"
```

4. **Process Offseason**
```bash
# Player development
curl -X POST "http://localhost:8000/development/process-offseason"

# Trade deadline
curl -X POST "http://localhost:8000/trades/deadline-simulation"  

# Advance to next season
curl -X POST "http://localhost:8000/draft/advance-offseason?completed_season=2024"
```

5. **Save Progress**
```bash
curl -X POST "http://localhost:8000/franchise/save?save_name=season_2024_complete&description=Completed 2024 season"
```

This creates a complete franchise simulation with realistic progression, AI decision-making, and persistent state management.
