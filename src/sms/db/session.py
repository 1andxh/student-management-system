from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from sms.core.config import settings

# NullPool + pool_pre_ping: no connection reuse across requests, and every
# connection that IS reused gets a liveness check first. Costs a fresh
# connection setup per request instead of a warm pool, but this project's
# dev environment restarts the DB container independently of the API
# container often enough (WSL2 idle-shutdown, rebuilds) that a long-lived
# pooled connection going stale underneath a request is the likelier
# failure mode to guard against here.
engine = create_async_engine(
    settings.database_url,
    echo=settings.env == "local",
    poolclass=NullPool,
    pool_pre_ping=True,
)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
