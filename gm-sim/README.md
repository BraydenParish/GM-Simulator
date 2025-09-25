# GM Simulator

A comprehensive NFL franchise management simulator backend built with FastAPI, SQLAlchemy, and modern Python. Features complete season simulation, AI-driven narratives, advanced trade logic, player development, and multi-season persistence.

## 🏈 Features

### Core Simulation
- **Realistic Game Simulation**: Drive-by-drive results with Elo-based win probabilities
- **Full Season Orchestration**: Schedule generation, multi-week simulation, playoff scenarios
- **AI Narrative Generation**: OpenRouter LLM integration for game recaps and storylines

### Team Management  
- **Comprehensive Roster Management**: 53-man rosters, practice squad, gameday actives
- **Salary Cap System**: Contract structuring, dead money, cap space tracking
- **Depth Chart Management**: Position-specific depth and snap count planning

### Player Systems
- **Advanced Player Development**: Age-based progression/decline with position-specific curves
- **Injury & Fatigue Modeling**: Realistic injury rates, recovery times, and performance impact  
- **Comprehensive Statistics**: Per-game and season stats with historical tracking

### Draft & Offseason
- **Intelligent Draft System**: AI-generated rookie classes with realistic attributes
- **Smart Draft AI**: Teams draft based on needs and best available talent
- **Contract Management**: Rookie scale contracts, extensions, free agency

### Trade Engine
- **Advanced Trade Evaluation**: Multi-factor value calculation beyond simple ratings
- **AI Trade Logic**: Teams make realistic offers based on needs and value
- **Trade Deadline Simulation**: League-wide trading with intelligent AI behavior

### Franchise Persistence
- **Save/Load System**: Complete franchise state preservation across sessions
- **Multi-Season Continuity**: Progress through multiple seasons with persistent history
- **Season Archives**: Historical data preservation with space-efficient storage

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Poetry (recommended) or pip

### Installation

1. **Clone and setup**
   ```sh
   git clone <repository-url>
   cd gm-sim
   pip install poetry
   poetry install
   ```

2. **Initialize database**
   ```sh
   make seed
   ```

3. **Start the server**
   ```sh
   make dev
   ```

4. **Explore the API**
   - Interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs)
   - Alternative docs: [http://localhost:8000/redoc](http://localhost:8000/redoc)

5. **Launch the lightweight web client**
   - Visit [http://localhost:8000/](http://localhost:8000/) for a minimal control center.
   - Click **Initialize Season** to auto-generate a schedule, then **Simulate Next Week** to advance.
   - Standings, progress, and narrative recaps update after every simulation.

### Optional: Enable AI Narratives
```sh
export OPENROUTER_API_KEY="your-api-key"
```

## 📋 Usage Examples

### Simulate a Complete Season
```python
import requests

# Generate schedule
requests.post("http://localhost:8000/seasons/generate-schedule", params={"season": 2024})

# Simulate full season with narratives
requests.post("http://localhost:8000/seasons/simulate-full", params={
    "season": 2024,
    "generate_narratives": True,
    "use_injuries": True
})

# Check final standings
standings = requests.get("http://localhost:8000/seasons/standings", params={"season": 2024})
```

### Conduct a Draft
```python
# Generate rookie class
rookies = requests.post("http://localhost:8000/draft/generate-rookies", params={"year": 2024})

# Let AI conduct the draft
draft_results = requests.post("http://localhost:8000/draft/conduct", params={
    "year": 2024,
    "auto_draft": True
})
```

### Drive an LLM Assistant Workflow
```python
import requests

# Surface a consolidated dashboard for the chat agent
dashboard = requests.get(
    "http://localhost:8000/assistant/season-dashboard",
    params={"season": 2025, "free_agent_limit": 5},
).json()

# Inspect projected free-agent targets for the upcoming offseason
projections = requests.get(
    "http://localhost:8000/assistant/free-agents/projections",
    params={"season": 2025},
).json()

# Sign a free agent with an even cash-flow contract constructed for the LLM
signing = requests.post(
    "http://localhost:8000/assistant/free-agents/sign",
    json={
        "player_id": 123,
        "team_id": 5,
        "start_year": 2025,
        "years": 3,
        "total_value": 36000000,
        "signing_bonus": 12000000,
    },
).json()

# Pull big-play highlights from a simulated matchup to narrate the recap
highlights = requests.get("http://localhost:8000/assistant/games/42/highlights").json()
```

### Evaluate Trades
```python
# Get team needs
needs = requests.get("http://localhost:8000/trades/team-needs/1")

# Generate AI trade offers
offers = requests.post("http://localhost:8000/trades/generate-offers/1")

# Simulate trade deadline
deadline = requests.post("http://localhost:8000/trades/deadline-simulation")
```

## 🏗️ Architecture

### Project Structure
```
gm-sim/
├── app/
│   ├── models.py          # SQLAlchemy database models
│   ├── schemas.py         # Pydantic request/response schemas  
│   ├── routers/           # FastAPI route handlers
│   │   ├── teams.py       # Team management
│   │   ├── players.py     # Player operations
│   │   ├── games.py       # Game simulation
│   │   ├── seasons.py     # Season orchestration
│   │   ├── draft.py       # Draft system
│   │   ├── trades.py      # Trade evaluation
│   │   ├── development.py # Player development
│   │   └── franchise.py   # Save/load system
│   └── services/          # Business logic
│       ├── sim.py         # Game simulation engine
│       ├── season.py      # Season management
│       ├── draft.py       # Draft logic
│       ├── trade_ai.py    # Advanced trade system
│       ├── development.py # Player progression
│       ├── injuries.py    # Injury simulation
│       ├── llm.py         # AI narrative generation
│       └── persistence.py # Save/load functionality
├── data/                  # Seed data and charts
├── tests/                 # Test suites
└── docs/                  # Documentation
```

### Key Technologies
- **FastAPI**: Modern, fast web framework with automatic OpenAPI generation
- **SQLAlchemy 2.0**: Async ORM with comprehensive relationship modeling
- **Pydantic**: Data validation and serialization with type hints
- **OpenRouter**: LLM integration for narrative generation

## 🧪 Testing

Run the test suite:
```sh
# All tests
poetry run pytest

# Integration tests only  
poetry run pytest tests/test_integration.py

# With coverage
poetry run pytest --cov=app
```

## 🔧 Development

### Code Quality
The project uses modern Python tooling:
- **Black**: Code formatting
- **Ruff**: Fast linting
- **MyPy**: Type checking

Run quality checks:
```sh
make lint    # Run all checks
ruff check . # Linting only
black .      # Format code
mypy app     # Type checking
```

### Database Migrations
For schema changes, the project uses SQLAlchemy's declarative approach. After model changes:

1. Update models in `app/models.py`
2. Run `make seed` to recreate with new schema (development)
3. For production, implement proper Alembic migrations

## 📊 API Overview

### Core Endpoints

| Endpoint | Purpose |
|----------|---------|
| `/teams/` | Team CRUD operations |
| `/players/` | Player management with filtering |
| `/games/simulate` | Single game simulation |
| `/seasons/simulate-full` | Complete season simulation |
| `/draft/conduct` | AI-driven draft process |
| `/trades/evaluate-proposal` | Advanced trade evaluation |
| `/development/process-offseason` | Player development |
| `/franchise/save` | Save franchise state |

See [docs/API_GUIDE.md](docs/API_GUIDE.md) for comprehensive documentation.

## 🎯 Roadmap

### Completed (90%+ Feature Complete)
- ✅ Core game simulation with realistic results
- ✅ Full season orchestration and scheduling  
- ✅ AI narrative generation integration
- ✅ Comprehensive draft system with rookie generation
- ✅ Advanced trade evaluation and AI logic
- ✅ Player development and aging systems
- ✅ Injury and fatigue modeling
- ✅ Multi-season persistence and save/load
- ✅ Salary cap management and contract system

### Future Enhancements
- **Playoff System**: Bracket generation and postseason simulation
- **Free Agency**: Realistic bidding and contract negotiations
- **Coaching Systems**: Scheme fits and coaching impact on development
- **Advanced Analytics**: EPA, win probability, and modern metrics
- **Web Interface**: React/Vue frontend for easier franchise management
- **Multiplayer**: Multi-user leagues with human GMs

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes with tests
4. Run quality checks (`make lint`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- **Jimmy Johnson Draft Value Chart**: For realistic pick valuations
- **nflfastR**: Inspiration for play-by-play data modeling  
- **Pro Football Reference**: Statistical modeling inspiration
- **OpenRouter**: LLM API integration for narrative generation

---

**Ready to build your dynasty?** Start with `make seed && make dev` and begin your franchise simulation journey!
