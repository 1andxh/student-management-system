# 0002. Domain-oriented architecture with repository pattern and centralized error handling

## Status
Accepted

## Context
The initial architecture pass proposed a conventional layered structure — top-level `models/`, `repositories/`, `services/`, `schemas/`, `api/v1/routers/` directories, each holding every domain's code mixed together (matching the shape of `full-stack-fastapi-template`). This was revised twice during planning:

1. First, the persistence layer was pushed toward an explicit repository pattern ("implement the repository pattern, it should handle persistence of aggregates in support of the domains") rather than bare CRUD functions scattered through routers.
2. Then the top-level layering itself was rejected in favor of package-by-feature ("use the domain architecture not layered, each domain should have their routes pointing to a main router.py so the entrypoint imports only one route and stays thin"), bundled with a request to add a project-wide custom exception hierarchy, exception handlers for validation and general errors, request-logging middleware, and structlog.

## Decision
- **Domain-oriented (package-by-feature) layout**: each domain (`students`, `teachers`, `terms`, `classes`, `enrollment`, `grades`, ...) is a self-contained package under `src/sms/domains/<name>/` owning its own `models.py`, `schemas.py`, `repository.py`, `service.py`, `router.py`, and `exceptions.py`. Cross-cutting concerns live in `src/sms/core/` and `src/sms/db/`, not duplicated per domain.
- **Repository pattern per aggregate root**: each domain's `repository.py` implements the shared `AbstractRepository[T]` (`src/sms/core/repository.py` — `add`, `get`, `list`, `remove`), plus domain-meaningful lookups (e.g. `get_by_email`). This is what makes service-level unit tests possible against an in-memory fake repository, independent of Postgres.
- **Unit of Work is deliberately deferred**, not built preemptively — it's the natural pairing with the repository pattern once a use case genuinely spans two aggregates in one transaction (expected at Stage 6, enrollment), but no domain built so far needs it.
- **Single router aggregator**: `src/sms/api/router.py` collects every domain's router via `include_router(...)`; `src/sms/main.py` only ever imports that one module, so the entrypoint never grows with the domain count.
- **Project-wide exception hierarchy**: `AppException` base (`message`, `status_code`) in `src/sms/core/exceptions.py`, with `NotFoundError`/`ConflictError`/`UnauthorizedError`/`PermissionDeniedError` as common subclasses domains raise directly or subclass further (e.g. `StudentNotFoundError(NotFoundError)`). Services raise these; routers never construct `HTTPException` by hand.
- **Three registered exception handlers** (`src/sms/core/exception_handlers.py`): one for `AppException` (maps `status_code`/`message` to a consistent JSON body), one for `RequestValidationError` (structured per-field errors), and a catch-all for `Exception` (logs the full exception, returns a generic safe 500 body).
- **structlog + request-logging middleware**: `src/sms/core/logging.py` configures structlog through stdlib logging (console renderer locally, JSON renderer otherwise); `src/sms/core/middleware.py` binds a request-id into structlog's contextvars per request and logs method/path/status/duration on completion.
- **Data-layer convention**: model constraints (uniqueness, checks) are declared via `__table_args__`, not bare `unique=True` on columns, so every invariant the database enforces is visible in one place per model.

## Consequences
- Adding a new domain means adding a new package under `domains/` plus one `include_router(...)` line in `api/router.py` — it should never require touching `main.py` or any other domain's code.
- A repository's job is "persist/retrieve this aggregate" — generic CRUD-style repository methods with no domain meaning should be treated as a smell, not the norm.
- No domain should introduce its own error-handling or logging convention; new error types must extend the existing `AppException` hierarchy rather than raising bare exceptions or FastAPI's `HTTPException` directly.
- Revisiting the "no Unit of Work yet" decision should happen once Stage 6 (enrollment) is actually reached and a real cross-aggregate transaction need materializes — not before, and not because it seems like good practice in the abstract.
