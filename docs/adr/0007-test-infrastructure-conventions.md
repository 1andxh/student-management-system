# 0007. Test infrastructure conventions: factory fixtures and unit/integration split

## Status
Accepted

## Context
Two testing conventions were settled during Stage 2, both raised directly by the user rather than pre-planned:

1. Stage 1 established shared test setup helpers (`create_student_via_db`, and Stage 2's `create_user_via_db`/`auth_headers`) as plain functions, explicitly imported into each test file (`from tests.conftest import ...`). This required `tests/__init__.py` and `tests/domains/__init__.py` to exist so the import path resolved — their absence caused a real `ModuleNotFoundError` mid-stage. The user then asked directly why these weren't pytest factory fixtures instead.
2. Each domain's tests lived flat as `tests/domains/<name>/test_service.py` (unit, fake repository) and `test_router.py` (integration, real Postgres) side by side. The user asked for these to be explicitly separated into unit/integration.

## Decision
- **Shared test setup helpers are factory fixtures, not plain imported functions.** `tests/conftest.py` defines `make_user` and `auth_headers` as `@pytest.fixture`s returning callables; domain-local equivalents (e.g. `make_student` in `tests/domains/students/integration/test_router.py`) follow the same pattern, defined locally until a second domain needs them, at which point they're promoted to the shared `conftest.py`. Pytest auto-discovers fixtures via its own conftest mechanism — no cross-file imports needed, which also sidesteps the import-path fragility that caused the `ModuleNotFoundError` above.
- **Each domain's tests are split into `unit/` and `integration/` subdirectories**: `tests/domains/<name>/unit/test_service.py` (fake in-memory repository, no database) and `tests/domains/<name>/integration/test_router.py` (real Postgres via `db-test`, through the actual HTTP layer). This is a per-domain split, not a top-level one — keeping `domains/` as the primary grouping stays consistent with ADR 0002's domain-oriented architecture; unit vs. integration is a secondary axis within each domain, not a competing top-level structure that would scatter one domain's tests across the repo.
- **Every test subdirectory needs its own `__init__.py`.** Multiple domains have identically-named files (`test_service.py`, `test_router.py` in both `auth/` and `students/`) — without `__init__.py` at every level, pytest's default import mode can't disambiguate same-named modules in different directories and errors out.

## Consequences
- Any new domain's tests should be created directly under `tests/domains/<name>/unit/` and `tests/domains/<name>/integration/` from the start, not flat, and should get an `__init__.py` at every new directory level without exception.
- A shared setup helper needed by more than one domain's tests belongs in the top-level `tests/conftest.py` as a factory fixture; a helper only one domain's tests use can stay local to that domain's own test file (or a domain-local `conftest.py` if it's needed by both `unit/` and `integration/` within that domain).
- Plain importable helper functions in `conftest.py` (the Stage 1/early-Stage-2 pattern) are superseded — don't reintroduce them by habit when copying an older test file as a starting point for a new domain.
