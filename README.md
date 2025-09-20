# GM Simulator

A minimal NFL GM simulator backend using FastAPI, SQLAlchemy, and Pydantic. Simulates teams, players, contracts, trades, and games with Elo and Jimmy Johnson draft value logic.

## Quick Start

1. **Install dependencies**
   ```sh
   pip install poetry
   poetry install
   ```

2. **Seed the database**
   ```sh
   make seed
   ```

3. **Run the server**
   ```sh
   make dev
   ```

4. **Visit the API docs**
   - Open [http://localhost:8000/docs](http://localhost:8000/docs)

## Project Structure

- `app/` - Main application code
- `data/` - Seed and chart data
- `Makefile` - Dev commands

## Endpoints
- CRUD for teams, players, contracts, depth chart, picks, transactions, games, standings
- Simulate games, advance week, evaluate trades, apply transactions

## Requirements
- Python 3.11+

---

See `/docs` for full OpenAPI documentation.
