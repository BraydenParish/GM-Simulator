from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from app.routers import (
    assistant,
    teams,
    players,
    depth,
    contracts,
    picks,
    transactions,
    games,
    injuries,
    standings,
    roster,
    seasons,
    draft,
    development,
    trades,
    franchise,
    playoffs,
)

app = FastAPI(title="GM Simulator", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"

if frontend_dir.exists():
    app.mount("/client", StaticFiles(directory=frontend_dir), name="client")

    @app.get("/", response_class=FileResponse)
    async def serve_frontend() -> FileResponse:
        """Serve the minimal web client for quick manual play."""
        return FileResponse(frontend_dir / "index.html")

app.include_router(teams.router)
app.include_router(players.router)
app.include_router(depth.router)
app.include_router(contracts.router)
app.include_router(picks.router)
app.include_router(transactions.router)
app.include_router(games.router)
app.include_router(injuries.router)
app.include_router(standings.router)
app.include_router(roster.router)
app.include_router(seasons.router)
app.include_router(draft.router)
app.include_router(development.router)
app.include_router(trades.router)
app.include_router(franchise.router)
app.include_router(playoffs.router)
app.include_router(assistant.router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
