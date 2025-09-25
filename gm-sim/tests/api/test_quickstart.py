import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import get_db
from app.main import app
from app.models import Base, Team


@pytest.fixture
async def test_sessionmaker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield session_factory
    finally:
        app.dependency_overrides.pop(get_db, None)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
async def client(test_sessionmaker):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_quickstart_initializes_schedule_and_tracks_progress(client, test_sessionmaker):
    async with test_sessionmaker() as session:
        teams = [
            Team(name=f"Team {index}", abbr=f"T{index:02d}")
            for index in range(1, 5)
        ]
        session.add_all(teams)
        await session.commit()

    quickstart_response = await client.post("/seasons/quickstart", params={"season": 2025, "weeks": 2})
    assert quickstart_response.status_code == 200
    quickstart_payload = quickstart_response.json()
    assert quickstart_payload["schedule_created"] is True
    assert quickstart_payload["scheduled_weeks"] == 2
    assert quickstart_payload["next_week"] == 1

    progress_response = await client.get("/seasons/progress", params={"season": 2025})
    assert progress_response.status_code == 200
    progress_payload = progress_response.json()
    assert progress_payload["scheduled_weeks"] == 2
    assert progress_payload["next_week"] == 1
    assert progress_payload["completed_weeks"] == 0

    simulate_response = await client.post(
        "/seasons/simulate-week",
        params={"season": 2025, "week": 1, "generate_narratives": False},
    )
    assert simulate_response.status_code == 200

    post_progress = await client.get("/seasons/progress", params={"season": 2025})
    assert post_progress.status_code == 200
    post_payload = post_progress.json()
    assert post_payload["last_completed_week"] == 1
    assert post_payload["next_week"] == 2
    assert post_payload["completed_weeks"] == 1

    second_quickstart = await client.post("/seasons/quickstart", params={"season": 2025})
    assert second_quickstart.status_code == 200
    second_payload = second_quickstart.json()
    assert second_payload["schedule_created"] is False
    assert second_payload["next_week"] == 2
