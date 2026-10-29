import os
from collections.abc import AsyncIterator

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://family:family@localhost:5432/family_test",
)
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-long-enough-for-hs256-123456")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")
os.environ.setdefault("PANEL_URL", "http://localhost:5173")
os.environ["TELEGRAM_BOT_TOKEN"] = ""

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import SessionFactory, engine  # noqa: E402
from app.main import create_app  # noqa: E402

TABLES = "refresh_tokens, login_codes, expenses, family_members, families, users"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def prepare_database() -> AsyncIterator[None]:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_tables() -> AsyncIterator[None]:
    yield
    async with SessionFactory() as session:
        await session.execute(text(f"TRUNCATE {TABLES} CASCADE"))
        await session.commit()


@pytest_asyncio.fixture
async def db():
    async with SessionFactory() as session:
        yield session


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
