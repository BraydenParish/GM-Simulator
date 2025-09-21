from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import (
    teams,
    players,
    depth,
    contracts,
    picks,
    transactions,
    games,
    standings,
    roster,
    seasons,
    draft,
    development,
    trades,
    franchise,
)

app = FastAPI(title="GM Simulator", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(teams.router)
app.include_router(players.router)
app.include_router(depth.router)
app.include_router(contracts.router)
app.include_router(picks.router)
app.include_router(transactions.router)
app.include_router(games.router)
app.include_router(standings.router)
app.include_router(roster.router)
app.include_router(seasons.router)
app.include_router(draft.router)
app.include_router(development.router)
app.include_router(trades.router)
app.include_router(franchise.router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
