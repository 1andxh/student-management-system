import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import every domain's models module here so Base.metadata sees their
# tables for autogenerate — added one line per domain as each is built.
from sms.core.config import settings
from sms.db.base import Base
from sms.domains.audit import models as audit_models  # noqa: F401
from sms.domains.auth import models as auth_models  # noqa: F401
from sms.domains.students import models as students_models  # noqa: F401
from sms.domains.users import models as users_models  # noqa: F401

target_metadata = Base.metadata

# Single explicit switch for which database migrations run against — never
# an implicit fallback. Unset or ALEMBIC_TARGET=dev -> dev DB (the safe
# default for manual CLI use). ALEMBIC_TARGET=test is required to touch the
# test DB; conftest.py sets it before invoking migrations for the test
# suite. Anything else fails loudly rather than guessing.
alembic_target = os.getenv("ALEMBIC_TARGET", "dev")
if alembic_target == "dev":
    db_url = settings.database_url
elif alembic_target == "test":
    db_url = settings.database_url_test
else:
    raise RuntimeError(
        f"Unknown ALEMBIC_TARGET={alembic_target!r} — expected 'dev' or 'test'."
    )

config.set_main_option("sqlalchemy.url", db_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
