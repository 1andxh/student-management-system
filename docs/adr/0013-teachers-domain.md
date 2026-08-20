# 0013. Teachers domain

## Status
Accepted

## Context
Stage 3 of the build plan: the first new domain built on top of the auth/users split (ADR 0012). Follows the same models/schemas/repository/service/router/exceptions shape as every prior domain (ADR 0002), built via the established TDD-delegation pattern — contract settled first, `qa-engineer` dispatched to write tests in parallel with implementation in the main thread.

## Decision
- **`Teacher` mutations are `ADMIN`-only, not `ADMIN`+`TEACHER`** — raised as an explicit question before implementation rather than defaulting to Students' precedent. `Teacher` records are staff/HR data (hire_date, the link to a login account) — a different trust tier than academic content, matching the reasoning already established for `Users` (ADR 0010): a teacher shouldn't be able to edit their own or a peer's HR record. Reads stay open to any authenticated user (`get_current_user`), same as Students — teacher directory info isn't sensitive the way mutation rights are.
- **`Teacher.user_id` is nullable, unique, `ON DELETE SET NULL`** — a `Teacher` can exist with no linked login yet (per the plan's "optionally linked to a User"), and if the linked account is ever removed, the HR record should outlive it rather than cascade-delete — same reasoning already anticipated in ADR 0011's own note about `Teacher`/`Student` rows linked via `user_id`. There is no `DELETE /users/{id}` route today, so this FK behavior isn't exercised via the API yet, but it's the correct default at the DB level regardless.
- **No rate limiting on `/teachers` routes** — consistent with Students/Audit precedent; rate limiting in this codebase is applied specifically to auth-adjacent surfaces (login brute-force, account creation abuse on `/users`), not uniformly to every domain.
- **No `security-auditor` review dispatched for this stage** — `Teacher` consumes the already-reviewed `require_role`/`get_current_user` RBAC mechanism without modifying it, the same position Students was in (which also didn't get a dedicated review). The project's "review any change touching auth/sessions/secrets/RBAC" rule is about changes to that machinery, not every consumer of it.

## Consequences
- A future domain modeled on "staff/account-adjacent data" (if one comes up) should default to the `Users`/`Teachers` ADMIN-only tier rather than Students' ADMIN+TEACHER tier — the fork was decided deliberately here, not left inconsistent.
- Stage 3b (teacher self-service change requests — see the plan) will need a `GET /teachers/me` lookup and a new model, not a loosening of `Teacher`'s own mutation gate — the ADMIN-only boundary on direct `PATCH /teachers/{id}` stays as-is; the change-request flow is an additive, separately-gated path.
- 118/118 tests passing (94 pre-existing + 24 new), full suite re-verified directly, not inferred from the delegated test-writer's own report.
