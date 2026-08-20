# 0016. Subjects and classes

## Status
Accepted

## Context
Stage 5 of the build plan. `Class` is the first aggregate that references three other domains at once (`Subject`, `Term`, `Teacher`) rather than at most one. Built via the same TDD-delegation pattern as every prior domain.

## Decision
- **One domain, two aggregates** — `domains/classes/` owns both `Subject` and `Class`, same shape as `domains/academic_years/` (ADR 0015): two `APIRouter` instances in one `router.py`, both registered in `api/router.py`.
- **Mutations are `ADMIN`-only** — raised as an explicit question before building, since the plan didn't state a tier for this stage the way it did for Stage 4. Subject codes and class scheduling (term/teacher assignment, capacity, room) are structural/registrar-level data, same tier as `Teachers` and `AcademicYear`/`Term`, not day-to-day content a teacher edits directly.
- **`Class`'s three FKs (`subject_id`, `term_id`, `teacher_id`) are `ON DELETE RESTRICT`, not `CASCADE`** — the opposite call from `Term`→`AcademicYear` (ADR 0015), deliberately. `Class` is the aggregate Stage 6 (Enrollment) and Stage 7 (Assessment) will reference next; letting a `Subject`/`Term`/`Teacher` deletion silently cascade through `Class` risks destroying scheduling data with a blast radius `Term` never had. `RESTRICT` forces an explicit reassignment or cleanup first.
- **`Class` has no uniqueness constraint at all** — per the plan's own explicit note, a teacher can run two sections of the same subject in one term; this iteration doesn't model sections. `ClassService.create()`/`update()` therefore have no `IntegrityError`→`AlreadyExists` translation (there's no such exception for `Class`) and no pre-check — the only validation is that the referenced `Subject`/`Term`/`Teacher` actually exist.
- **`capacity` is Pydantic-validated (`Field(gt=0)`), not just DB-`CHECK`-validated** — a deliberate departure from every prior domain's pattern (which relied solely on the DB `CHECK` constraint, e.g. `Student.date_of_birth`). `capacity` is single-field validation, exactly what Pydantic is suited for (matches the existing precedent of `UserCreate.password: Field(min_length=8)`), so there's no reason to route it through an `IntegrityError` catch when a clean 422 is available for free.
- **`ClassService` depends on `TeacherRepository` (teachers domain) and `TermRepository` (academic_years domain) directly** — the first service in this codebase to depend on two other domains' repositories at once. This is a one-way fan-in, not a cycle (neither `teachers` nor `academic_years` depends back on `classes`), so it doesn't violate the dependency-free-core pattern established for `audit`/`users` (ADR 0011/0012) — that pattern is specifically about avoiding circular references, not about a service never touching another domain's repository.

## Consequences
- Stage 6 (Enrollment) will need `class_id` existence validation the same way `ClassService` validates `subject_id`/`term_id`/`teacher_id` here — this is the established pattern for a new aggregate that fans into an existing one, not something to reinvent.
- If a `DELETE /subjects/{id}`, `/terms/{id}`, or `/teachers/{id}` is ever attempted while a `Class` still references it, the request fails with a DB-level FK violation (surfaces as an unhandled 500 today, since no domain exception currently wraps that specific case) rather than silently destroying the `Class`. Worth a cleaner error mapping (a `ReferencedByClassError`-style translation) if this becomes a real workflow, but not built preemptively here.
- 251/251 tests passing (200 pre-Stage-5 + 51 new), independently re-verified after resolving a stale-container gap (the integration test file landed on disk after an intermediate rebuild, so `docker compose up -d --build` had to run twice before the full 51 were collected) — not inferred from the delegated test-writer's own report.
