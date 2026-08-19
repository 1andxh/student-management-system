import os
from collections.abc import AsyncGenerator

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from sms.core.config import settings
from sms.core.rate_limit import limiter
from sms.core.security import create_access_token, hash_password
from sms.db.session import get_db
from sms.domains.auth.models import User, UserRole
from sms.main import create_app


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    """limiter (sms.core.rate_limit) is a module-level singleton, so its
    in-memory counters persist across tests even though `client` builds a
    fresh app each time — without this, tests hitting a rate-limited route
    from the same synthetic client IP would silently accumulate against one
    shared bucket instead of being independent. Same isolation principle as
    db_session's SAVEPOINT rollback, applied to in-memory state instead."""
    limiter.reset()


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


@pytest.fixture
def make_user(db_session: AsyncSession):
    """Factory fixture, shared across domains' tests: returns an async
    callable that inserts a User directly via the session (bypassing the
    auth service/router), so tests for *other* endpoints can set up an
    authenticated actor without depending on auth's own HTTP surface.
    db_session is captured here rather than passed at each call site.
    hashed_password defaults to a real argon2 hash of "password123" so
    login flows can authenticate against it; pass hashed_password=...
    directly to override with a pre-hashed value instead of a plaintext
    one."""

    async def _make_user(**overrides: object) -> User:
        defaults: dict[str, object] = {
            "email": "user@example.com",
            "hashed_password": hash_password("password123"),
            "role": UserRole.ADMIN,
            "is_active": True,
        }
        defaults.update(overrides)
        user = User(**defaults)
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    return _make_user


@pytest.fixture
def auth_headers():
    """Factory fixture: returns a callable that builds the bearer-token
    header for a given user, for use against endpoints protected by
    get_current_user/require_role."""

    def _auth_headers(user: User) -> dict[str, str]:
        token = create_access_token(user.id)
        return {"Authorization": f"Bearer {token}"}

    return _auth_headers
