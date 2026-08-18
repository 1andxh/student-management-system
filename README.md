# School Management System — Backend

## What this project actually is

This build exists to get hands-on reps with the agentic harness / agentic
orchestration workflow — checkpointed staged delivery, TDD discipline,
subagent delegation — not to produce a polished product. The school
management domain is a vehicle for that practice, not the point.

**The bar for any given stage is "works correctly and fits the stated
scope," not portfolio polish.** This is explicitly not a
production-hardening or portfolio exercise.

The full staged roadmap and architecture decisions live in the plan this
project was built from (see the owning session's plan file); this README
just states intent so it isn't lost in later sessions.

## Stack

- FastAPI + SQLAlchemy 2.0 (async, `asyncpg`)
- PostgreSQL (separate `db` / `db-test` instances)
- Alembic for migrations
- `uv` for dependency management
- `pytest` + `pytest-asyncio` + `httpx` for testing
- `structlog` for logging
- Docker Compose — `api`, `db`, `db-test` all run as services on the same
  network

## Running it

Everything runs via Docker Compose, from a WSL shell (host port-publishing
to Windows is broken on this machine's WSL Docker install — unrelated to
this project — so commands below assume you're already inside WSL, in this
project directory):

```sh
docker compose up -d --build
```

Common commands (run inside the `api` container):

```sh
# Apply migrations to the dev DB (defaults to dev; see alembic/env.py)
docker compose exec api uv run alembic upgrade head

# Generate a new migration after changing models
docker compose exec api uv run alembic revision --autogenerate -m "message"

# Run the test suite (applies migrations to db-test automatically)
docker compose exec api uv run pytest
```

Alembic's target database is controlled by a single explicit switch,
`ALEMBIC_TARGET` (`dev` default, `test` for the test DB) — see
`alembic/env.py`. The test suite sets this itself; you only need it if
running Alembic manually against the test DB.

## Project layout

Domain-oriented (package-by-feature), not layered by technical concern.
Each domain under `src/sms/domains/` owns its own model, repository,
service, schemas, router, and exceptions. Cross-cutting infrastructure
(config, logging, the exception hierarchy, the generic repository
abstraction, DB session) lives in `src/sms/core/` and `src/sms/db/`.
`src/sms/api/router.py` aggregates every domain's router so
`src/sms/main.py` stays a thin entrypoint that never grows with the domain
count.
