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

## Frontend (`web/`)

A Vite + React + TypeScript single-page app in `web/`, in the same repo as
the API (the backend stays at the root). Stack and layout rationale:
`docs/adr/0028`.

```sh
cd web
npm install
npm run dev        # http://127.0.0.1:5173 — expects the API on 127.0.0.1:8001
```

Use `127.0.0.1`, not `localhost`: the API's CORS allowlist and the refresh
cookie are tied to that exact origin. `--strictPort` is deliberate: if 5173
is taken, Vite fails instead of quietly moving to 5174, an origin the API
would reject.

Other scripts: `npm run typecheck`, `npm run lint`, `npm test`,
`npm run build`.

**API types are generated, not hand-written.** After any backend change
that touches a route or schema, run `npm run gen:api` (from `web/`) and
commit the updated `src/lib/api-schema.d.ts`. It dumps the OpenAPI schema
straight from the FastAPI app (`sms.scripts.dump_openapi`), so it needs `uv`
and a valid `.env`, but no running server or database. CI fails if the
committed file is stale.
