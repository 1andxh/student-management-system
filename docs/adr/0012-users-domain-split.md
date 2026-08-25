# 0012. Split users out of auth

## Status
Accepted

## Context
Admin/account-management endpoints (`POST/GET/PATCH /users`) had lived inside `domains/auth/` since Stage 2c, alongside login/refresh/logout/me — a pragmatic choice at the time since both touched the same `User` table. The user asked directly why admin routes were merged into auth. The answer (User has lived in auth since Stage 2; splitting would make a new domain depend back on auth anyway for RBAC, so there was no clean decoupling win without also moving the model) was explained, and the response was explicit: split it now, before the rest of the plan (Teachers, Terms, Classes, Enrollment, Grades) builds more code on top of the merged shape and makes the split more expensive later.

## Decision
- **New `domains/users/` domain owns account data and admin CRUD**: `User`/`UserRole` model, `UserRepository` (including `count_active_super_admins`'s locking read), `UserService` (create/get/list/update, admin-tier protection, last-active-super-admin invariant), `UserCreate`/`UserRead`/`UserUpdate` schemas, and the `POST/GET/GET{id}/PATCH{id} /users` routes — moved verbatim from `domains/auth/`, no behavior changes.
- **`domains/auth/` is stripped down to session/token concerns only**: `Session` model, `SessionRepository`, `AuthService` (login/refresh/logout), `LoginRequest`/`TokenResponse`/`RefreshRequest`/`LogoutRequest` schemas, `get_current_user`/`require_role` dependencies, and the `/auth/login|refresh|logout|me` routes.
- **Dependency direction is one-way: `auth` depends on `users`, not the reverse** — `AuthService` and the RBAC dependencies (`get_current_user`, `require_role`) import `User`/`UserRole`/`UserRepository` from `sms.domains.users`. `users`' own core (models/schemas/repository/service) imports nothing from `auth`; only `users/router.py` imports `auth.dependencies` for RBAC gating on its routes — same pattern as every other domain's router (audit, students), and the same dependency-free-core shape already proven for `domains/audit/` in ADR 0011. Verified non-circular directly (`python -c "import sms.domains.users"` and `import sms.domains.auth` both succeed standalone).
- **`Session.user_id`'s `ForeignKey("users.id")` stays a plain string reference** — no Python import of `User` needed on the auth side for this; SQLAlchemy resolves FKs by table name at mapper-configuration time, not by import.
- **Every other domain that referenced `UserRole` for route gating (`students`, `audit`) now imports it from `sms.domains.users`** instead of `sms.domains.auth` — a one-line import change per file, no logic change.

## Consequences
- A future domain that only needs to check `UserRole` (not touch sessions/tokens) can depend on `users` alone, without pulling in auth's session/JWT machinery — the split this ADR makes is exactly the boundary that was missing before.
- `auth`'s own tests (`tests/domains/auth/`) cover only `AuthService`/session/login/refresh/logout/me; account-management tests (`UserService`, `/users/*` HTTP) moved to new `tests/domains/users/unit/` and `tests/domains/users/integration/` packages, each with their own `__init__.py` per ADR 0007's disambiguation requirement.
- `alembic/env.py`, `tests/conftest.py`'s `make_user` fixture, and `scripts/create_admin.py` now import `User`/`UserRole`/`UserRepository`/`UserCreate`/`UserService`/`UserAlreadyExistsError` from `sms.domains.users`, not `sms.domains.auth` — any future script or migration touching account data should import from `users`, not `auth`.
- No migration was needed — this is a pure Python-package reorganization; the `users` table's name, columns, and constraints are unchanged.
- Full suite re-verified green after the split (94/94), confirming the move preserved behavior exactly rather than just moving files around unverified.
