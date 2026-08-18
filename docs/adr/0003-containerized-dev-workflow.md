# 0003. Containerized dev workflow with explicit migration targeting

## Status
Accepted

## Context
The original plan called for Postgres (dev + test) running in Docker via `docker-compose.yml`, with app code and tests running **locally** via `uv run pytest` / `uv run fastapi dev`, connecting to the dockerized Postgres over an exposed host port. During Stage 0 implementation, this broke down: on this machine, WSL2 Docker's host→container port-publishing was unreliable (containers healthy, `docker-proxy` listening, but connections refused even from *within* WSL, confirmed by testing the same failure against the user's other already-running, normally-working projects). Container-to-container communication over the Docker network, by contrast, worked immediately and consistently — which is how the user's existing projects are normally run (`docker compose up --build`, everything containerized).

Separately, once Alembic was wired up, a real risk was flagged: nothing distinguished an intentional "run migrations against the test DB" action from the implicit default, meaning a manually-run migration command could silently hit the wrong database.

## Decision
- **The app itself is a `docker-compose` service** (`api`), on the same network as `db`/`db-test`, connecting to them by container hostname (`db:5432`, `db-test:5432`) — not via host-published ports. The whole stack runs via `docker compose up --build`, matching the user's established workflow. One-off commands (`alembic`, `pytest`) run via `docker compose exec api uv run ...`.
- **Only `./alembic/versions` is bind-mounted** into the `api` container — not the full source tree. This project rebuilds the image on code change (`docker compose up --build`) rather than hot-reloading; the scoped mount exists solely so `alembic revision --autogenerate` output (generated inside the container) lands on the host/git instead of being stranded in the container's filesystem.
- **A single explicit switch, `ALEMBIC_TARGET`** (`dev` default, `test` for the test DB), controls which database `alembic/env.py` targets — never an implicit default silently picked based on caller context. `tests/conftest.py`'s migration fixture sets `ALEMBIC_TARGET=test` before invoking Alembic, using the exact same switch a manual CLI run would use. An unrecognized value raises rather than guessing.
- Host port-publishing being broken on this machine is treated as environment flakiness, not a project bug — not something to keep re-diagnosing.

## Consequences
- There is no "run the app locally against Docker Postgres" dev loop anymore; every app/test run goes through the `api` container. A contributor without Docker running gets nothing.
- Any future container that generates files meant to be reviewed/committed (not just `alembic/versions`) needs its own explicit bind mount, following the same reasoning — it won't happen automatically.
- Running Alembic manually against the test database requires explicitly typing `ALEMBIC_TARGET=test`; forgetting it is safe (falls back to dev), but there is intentionally no convenience shortcut that could make hitting the wrong database easy.
