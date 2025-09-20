from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Player
from app.schemas import PlayerCreate, PlayerListResponse, PlayerRead

PLAYER_LIST_EXAMPLE = {
    "items": [
        {
            "id": 1,
            "name": "Alice Runner",
            "pos": "RB",
            "team_id": 1,
            "ovr": 78,
        },
        {
            "id": 2,
            "name": "Bob Thrower",
            "pos": "QB",
            "team_id": 1,
            "ovr": 82,
        },
    ],
    "total": 2,
    "page": 1,
    "page_size": 25,
}

PLAYER_LIST_ERROR_EXAMPLE = {
    "detail": [
        {
            "type": "less_than_equal",
            "loc": ["query", "page_size"],
            "msg": "Input should be less than or equal to 100",
            "input": 101,
            "ctx": {"le": 100},
        }
    ]
}

router = APIRouter(prefix="/players", tags=["players"])


@router.get(
    "/",
    response_model=PlayerListResponse,
    summary="List players",
    description=(
        "Return a paginated list of players with optional filters for team, position, "
        "and a case-insensitive name search."
    ),
    responses={
        200: {"content": {"application/json": {"example": PLAYER_LIST_EXAMPLE}}},
        422: {
            "description": "Validation error",
            "content": {"application/json": {"example": PLAYER_LIST_ERROR_EXAMPLE}},
        },
    },
)
async def list_players(
    page: int = Query(1, ge=1, description="1-indexed page number"),
    page_size: int = Query(
        25,
        ge=1,
        le=100,
        description="Number of results per page (maximum 100).",
    ),
    team_id: int | None = Query(None, description="Filter to a specific team id."),
    position: str | None = Query(None, description="Filter by exact position code (e.g., QB, RB)."),
    search: str | None = Query(
        None,
        min_length=1,
        description="Case-insensitive substring match against player names.",
    ),
    db: AsyncSession = Depends(get_db),
):
    filters = []

    if team_id is not None:
        filters.append(Player.team_id == team_id)

    if position:
        filters.append(func.lower(Player.pos) == position.lower())

    if search:
        like_pattern = f"%{search.lower()}%"
        filters.append(func.lower(Player.name).like(like_pattern))

    count_stmt = select(func.count(Player.id))
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = await db.scalar(count_stmt)
    if total is None:
        total = 0

    query = (
        select(Player)
        .where(*filters)
        .order_by(Player.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    players = result.scalars().all()

    items = [PlayerRead.model_validate(player) for player in players]

    return PlayerListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{player_id}", response_model=PlayerRead)
async def get_player(player_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Player).where(Player.id == player_id))
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return PlayerRead.model_validate(player)


@router.post("/", response_model=PlayerRead)
async def create_player(player_in: PlayerCreate, db: AsyncSession = Depends(get_db)):
    player = Player(**player_in.model_dump())
    db.add(player)
    await db.commit()
    await db.refresh(player)
    return PlayerRead.model_validate(player)


@router.put("/{player_id}", response_model=PlayerRead)
async def update_player(
    player_id: int, player_in: PlayerCreate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Player).where(Player.id == player_id))
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    for k, v in player_in.model_dump().items():
        setattr(player, k, v)
    await db.commit()
    await db.refresh(player)
    return PlayerRead.model_validate(player)


@router.post("/{player_id}/move", response_model=PlayerRead)
async def move_player(player_id: int, team_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Player).where(Player.id == player_id))
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    player.team_id = team_id
    await db.commit()
    await db.refresh(player)
    return PlayerRead.model_validate(player)
