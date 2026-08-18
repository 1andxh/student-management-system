import os
from collections.abc import AsyncGenerator

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from sms.core.config import settings
from sms.db.session import get_db
from sms.main import create_app


@pytest.fixture(scope="session", autouse=True)
def apply_migrations() -> None:
    """Brings the test database schema to head once per test session, so
    individual tests never need to think about migrations. ALEMBIC_TARGET
    is the same explicit switch alembic/env.py uses for the CLI — setting
    it here (rather than poking sqlalchemy.url directly) means there's
    exactly one mechanism controlling which DB migrations ever touch."""
    os.environ["ALEMBIC_TARGET"] = "test"
    try:
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
    finally:
        del os.environ["ALEMBIC_TARGET"]


@pytest.fixture(scope="session")
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(settings.database_url_test)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Each test runs inside one connection-level transaction plus a
    SAVEPOINT (join_transaction_mode="create_savepoint"): application code
    can call session.commit() as normal (releasing only the SAVEPOINT), and
    rolling back the outer connection transaction after the test undoes
    everything without recreating the schema per test."""
    async with test_engine.connect() as connection:
        await connection.begin()
        async with AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        ) as session:
            yield session
        await connection.rollback()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
