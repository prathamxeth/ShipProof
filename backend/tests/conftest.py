import pytest
import pytest_asyncio
import os
from pathlib import Path
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text

TEST_DB_FILE = Path("/tmp/test_shipproof.db")
TEST_DB_URL = f"sqlite+aiosqlite:///{TEST_DB_FILE}"

from backend.app.core.config import settings
settings.DATABASE_URL = TEST_DB_URL

# Rebind database engine & sessionmaker in backend.app.core.database to use TEST_DB_URL
import backend.app.core.database as app_db
app_db.engine = create_async_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
app_db.AsyncSessionLocal = async_sessionmaker(bind=app_db.engine, class_=AsyncSession, expire_on_commit=False)

from backend.app.models.entities import Base
from backend.app.main import app

@pytest_asyncio.fixture(scope="session", autouse=True)
async def init_session_db():
    if TEST_DB_FILE.exists():
        try:
            TEST_DB_FILE.unlink()
        except Exception:
            pass
    await app_db.init_db()
    yield
    await app_db.engine.dispose()
    if TEST_DB_FILE.exists():
        try:
            TEST_DB_FILE.unlink()
        except Exception:
            pass

from backend.app.core.auth import _rate_limit_records, create_session_token

@pytest_asyncio.fixture(scope="function", autouse=True)
async def clean_tables():
    _rate_limit_records.clear()
    yield
    _rate_limit_records.clear()
    # Clean all rows after each test without unlinking the file
    async with app_db.AsyncSessionLocal() as session:
        for tbl in ["repair_events", "repair_records", "verification_events", "verification_steps", "verification_runs", "projects"]:
            try:
                await session.execute(text(f"DELETE FROM {tbl};"))
            except Exception:
                pass
        await session.commit()

@pytest_asyncio.fixture
async def client():
    token = create_session_token("test-operator")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver", cookies={"shipproof_session": token}) as ac:
        yield ac

@pytest_asyncio.fixture
async def auth_client():
    transport = ASGITransport(app=app)
    token = create_session_token(username="test-operator")
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        cookies={"shipproof_session": token}
    ) as ac:
        yield ac

@pytest_asyncio.fixture
async def unauth_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
