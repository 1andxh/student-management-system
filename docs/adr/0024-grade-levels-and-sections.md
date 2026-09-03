# 0024. Grade levels, sections, and section-driven auto-enrollment

## Status
Accepted

## Context
A comparison against typical SIS/SMS feature sets surfaced a structural mismatch: students enrolled individually into `Class` rows — a *university course-registration* model — while `Student.guardian_name`/`guardian_phone` imply K-12. Confirmed with the user that this is a K-12 school, so students belong to a grade level and a section ("Grade 7, Section B"). This was the one gap that got more expensive every stage it was deferred, since Enrollment/Assessment/Grade/gradebook all hang off it.

Two forks were confirmed before building: section assignment **auto-creates `Enrollment` rows** (keeping Enrollment the single source of truth, so the gradebook, assessment scoping, capacity guards and ownership rules built in ADRs 0019/0022/0023 keep working untouched), and **promotion / year rollover is deferred** to its own stage.

## Decision

### Three aggregates in one `sections` domain
Same "related aggregates share a domain" precedent as `classes` (Subject+Class) and `academic_years` (AcademicYear+Term).

- **`GradeLevel`**: `name`, `rank`. Unique on both; `rank >= 0` (0 allows a Reception/Kindergarten year). `rank` is deliberately explicit rather than inferred from `name`, which varies by school ("Grade 7", "JSS 1", "Year 8") — and it's what a future promotion stage will walk.
- **`Section`**: unique on (`grade_level_id`, `academic_year_id`, `name`) — "7B" is unique *within an academic year*, since 7B in 2024-25 is a different cohort from 7B in 2025-26. `class_teacher_id` is nullable `SET NULL` (a section can exist before a homeroom teacher is assigned; removing a teacher must not destroy the section).
- **`SectionAssignment`**: unique (`student_id`, `academic_year_id`) — one section per student per year, as a real DB constraint. **`academic_year_id` is deliberately denormalised** from the section: Postgres can't express a uniqueness rule that reaches through a FK, and this codebase consistently prefers DB-enforced invariants (ADR 0004's reasoning). It is derived server-side from the section, appears on no request schema, and `SectionUpdate` omits `academic_year_id` entirely so a populated section can't be moved to another year and silently invalidate it.

### `Class.section_id` is nullable, and the sections domain owns attachment
Null = an individually-enrolled class (unchanged behavior). Set = taught to a whole section.

`section_id` is deliberately **absent from `ClassCreate`/`ClassUpdate`**. Attaching a class must back-fill Enrollment rows for the section's current members, which would make `classes/service.py` import the enrollments domain — while `enrollments/service.py` already imports `classes`, and both packages' `__init__.py` re-export their services. That's a genuine circular import, the same class of import-time breakage as ADR 0018/0019's annotation shadowing. Putting attachment in the sections domain leaves exactly one path that can set the column.

### Auto-enrollment
`SectionAssignmentService.assign` takes a locking read on the section (`get_for_update`, same pattern and reasoning as Enrollment's capacity guard in ADR 0017), checks capacity, inserts the assignment, then fans out one `Enrollment` per attached class — all under `commit=False` with one shared final `commit()` and `rollback()` on failure (ADR 0011's pattern).

**Per-class `capacity` is deliberately not enforced during auto-enrollment**: for a section-taught class the section's capacity is the governing constraint, and failing a section assignment because one of eight attached classes has a smaller capacity would be a confusing, unrelated failure. This holds *only* because re-attaching a class to a second section is now blocked (see below) — without that, rosters could stack on one class and the overshoot would be unbounded.

`detach_class` and `unassign` deliberately **leave existing `Enrollment` rows intact** — enrollment history is academic-record data, the same protective reasoning behind the RESTRICT FKs.

## Security review
A `security-auditor` pass confirmed the un-spoofability of `academic_year_id`, the atomicity of both fan-out paths, the capacity race-safety under READ COMMITTED, mutation RBAC, and the absence of injection surface. It found five issues, all fixed directly:

- **Roster leak (Medium).** `GET /sections/{id}/students` was open to any authenticated user. Left open it reconstructs by join exactly what ADR 0023 closed: the roster gives a STUDENT every classmate's `student_id`, `ClassRead` now exposes `section_id`, and assignment auto-enrolls the whole roster into every attached class — so roster + `GET /classes` rebuilds the student→classes mapping `EnrollmentService.list` refuses to serve a STUDENT directly. Now gated ADMIN+TEACHER, the same tier and reasoning as the gradebook (ADR 0022). Note this leak was partly *created* by this stage's own `ClassRead.section_id` addition.
- **No academic-year validation on `attach_class` (Medium).** A `Class` has no year of its own — it's reached via `Class.term_id → Term.academic_year_id`. Attaching a class from another year auto-enrolled the whole roster into it, handing that class's teacher gradebook read/write over an unrelated cohort from one mistyped UUID. Now validated, raising `ClassYearMismatchError`.
- **Silent re-attach (Medium).** Attaching an already-attached class re-pointed it, orphaning the first section's enrollments and stacking both rosters onto one class — unbounded overshoot of the per-class capacity that `EnrollmentService.enroll` takes a row lock to protect. Now `ClassAlreadyAttachedError`; re-pointing must be an explicit detach-then-attach.
- **`attach_class` took no lock (Low).** It raced a concurrent `assign`: both transactions read consistent-but-stale state, both commit, and the student ends up on the roster without an enrollment for that class — the invariant broken silently. Now takes the same `get_for_update` lock, so the two paths serialise.
- **`get_for_update` without `populate_existing` (Low, latent).** The lock is always taken, but an instance already in the session's identity map is returned unrefreshed, so a capacity read could predate the lock. Not reachable on current call paths (verified), but it reopens silently on any refactor that reads the row first. Fixed here and in `ClassRepository.get_for_update`.

Two suggestions were also applied: `detach_class` now raises rather than silently no-op'ing on a class that was never attached, and `assign`'s `except IntegrityError` no longer maps *every* integrity failure to "already assigned to a section" — it inspects the constraint name and re-raises anything else, so an FK violation or a fan-out duplicate doesn't send someone debugging down the wrong path.

## Consequences
- The `Class.section_id` nullable column means the system now supports both models simultaneously: section-taught classes and individually-enrolled electives. That was the point, but it means "who is in this class" has one source of truth (Enrollment) with two ways of getting there.
- A future promotion/rollover stage has what it needs: `GradeLevel.rank` to advance along, and `SectionAssignment.academic_year_id` to scope a cohort. `Student.enrollment_status` still has a `graduated` value nothing produces — that stays true until then.
- ~~`ClassService.update` can still change `term_id` on an attached class~~ **Resolved immediately after this stage.** `ClassService.update` now raises `ClassAttachedToSectionError` (409) on any `term_id` change while `section_id` is set. Chosen over injecting `SectionRepository` into `ClassService` to compare years: that would re-introduce the `classes → sections` import direction this stage avoided, and with both packages' `__init__.py` re-exporting their services it is a genuine cycle. Rejecting the change needs no new dependency at all — `Class.section_id` is already on the model — and matches the explicit detach-then-attach pattern already established for re-attach. A section-taught class is simply pinned to its section's year; detach first to move it.
- 566/566 tests passing. Note the count *fell* from 702 despite adding a whole domain — see `docs/adr/0025` for the test-strategy revision applied in the same pass.
