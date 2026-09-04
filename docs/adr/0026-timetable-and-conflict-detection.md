# 0026. Timetable, conflict detection, and where that invariant actually holds

## Status
Accepted

## Context
`Class` had a subject, term, teacher, room, capacity and section — but no *when*. Chosen as the stage after sections for being the one candidate whose logic is genuinely unlike the CRUD slices already built.

Two forks confirmed before building: **fixed periods / bell schedule** rather than free time ranges (how most K-12 schools actually run), and **teacher + room + section** double-booking all enforced.

Deliberately not built: "the slot falls within the class's term dates". A period-based slot is a *recurring weekly pattern* (`Monday, Period 3`), not a date, so there is no date to compare against term bounds — the check could never fail. Recorded rather than written as a no-op.

## Decision

### Two aggregates
- **`Period`** — the bell schedule, school-wide rather than per academic year (a bell schedule rarely changes, and tying it to a year would mean recreating every period and re-pointing every slot each September for nothing). Unique `name`, `end_time > start_time`, ordered by `start_time` — no separate rank column, because a bell schedule's order *is* its chronological order.
- **`ScheduleSlot`** — `(class_id, day_of_week, period_id)`, unique together. No date, no `updated_at`: a slot is created and deleted, never edited.

### Conflict detection is service-level, and that placement is the interesting decision
The three rules key off `Class.teacher_id`, `Class.room` and `Class.section_id` — none of which live on the slot. Making them DB constraints would mean denormalising all three onto `ScheduleSlot`. **The contrast with ADR 0024 is the point**: `SectionAssignment.academic_year_id` was denormalised precisely because its source is immutable by design (`SectionUpdate` omits it). `Class.teacher_id` and `Class.room` are the opposite — `PATCH /classes` can change both — so denormalised copies would go stale and the constraint would then enforce the wrong thing.

So conflicts are checked in `ScheduleSlotService` under a locking read, and each rule raises its own 409 (`TeacherDoubleBookedError`, `RoomDoubleBookedError`, `SectionDoubleBookedError`) so the caller learns *which* rule fired — "the teacher is busy" and "the room is taken" need different fixes from whoever is building the timetable.

A NULL room and a NULL section are exempt: "no room assigned" is not a resource two classes can contend for. The room comparison is an exact string match, because `Class.room` is nullable free text — so `"Lab 2"` and `"lab 2"` read as different rooms, and the rule is one keystroke from being bypassed. Enforced anyway (no check is worse), but **a real `Room` entity is the actual fix** and is its own stage.

### Overlapping periods — the hole that made all of the above bypassable
Found by `security-auditor`. Every conflict rule keys on `period_id`, not wall-clock time, and nothing stopped two `Period` rows covering the same time. So an admin could create "Period 3" (10:00–10:45) and "Period 3 Science" (10:00–10:45), then schedule the same teacher, the same room *and* the same section into both — all three checks pass, because they compare period identity rather than time. That defeats the entire feature through the documented API, with no error.

Closed with a Postgres **exclusion constraint** (`ex_periods_no_overlap`, `EXCLUDE USING gist (tsrange(...) WITH &&)`, requiring the standard `btree_gist` extension) rather than a service check, which would race itself. Times are lifted onto an arbitrary fixed date because Postgres has no native "time range" type; the date is identical for every row and only the time-of-day matters. `tsrange` is half-open, so back-to-back periods (09:45 end, 09:45 start) correctly do not overlap — there is a test pinning that, since an inclusive range would have been an easy mistake.

Confirmed with the user rather than assumed, because it has a real cost: a school running split bell schedules for different year groups genuinely cannot model that now. The alternative — comparing wall-clock times instead of period ids — was on the table and rejected as reintroducing the interval math the fixed-period model was chosen to avoid.

### `GET /timetable` requires at least one filter
Unfiltered, it returned the whole school's schedule, unpaginated, to any authenticated user. The auditor confirmed this is **not** a re-opening of ADRs 0023/0024 — no student identifier appears anywhere in the timetable response surface, so the student→section edge those ADRs protect is untouched. What it was: combined with the already-public `GET /classes`, any logged-in student could build a week-by-week physical-location map of every member of staff and every cohort in two requests. Requiring `class_id`, `teacher_id` or `section_id` preserves every legitimate view and removes the bulk scrape. A shared whole-school wall-timetable, if ever wanted, should be a deliberate endpoint rather than something that falls out of a missing filter.

### Other findings fixed in the same pass
- **`attach_class` raced slot creation.** They locked different rows (Section vs Period), so a class could pass the section check while `section_id` was still NULL and have it set moments later — two classes from one section in one slot, no error. Both paths now take a locking read on the **Class** row, which is what actually gives them a shared lock.
- **A fail-open guard whose comment claimed fail-closed.** `_check_conflicts` filtered out slots whose class had vanished while its own comment said it did the opposite. Now genuinely raises. Unreachable under RESTRICT today — which is exactly why it could have reopened unnoticed.
- **`PeriodService.update` raised a bare `ValueError`** — the only service in the codebase to raise a non-`AppException` — turning an ordinary bad-input PATCH into a 500 plus a traceback. Now `InvalidPeriodTimesError` (422). The check has to live in the service because a partial PATCH can only be validated against the stored row.
- **`DELETE /periods/{id}` on a period still timetabled** surfaced the RESTRICT `IntegrityError` as a 500. Now `PeriodInUseError` (409). The same gap exists in other domains' `remove()` methods; fixed here rather than swept codebase-wide unasked.

## Consequences
- **The conflict invariant holds at insert time only.** `PATCH /classes` can still change a class's teacher or room and create a conflict retroactively, with no error and no way to discover it except a manual scan. Closing it from `ClassService` needs the timetable repository, and importing it pulls in `sms.domains.timetable.__init__`, which re-exports the service, which imports classes — the same cycle ADR 0024 documented. The honest options are a reconciliation/report endpoint owned by the timetable domain, or restructuring the package exports. **Open, and the ADR text should not be read as promising more than the code does.**
- `get_latest_by_student_id` stands in for "the student's current section" because nothing in this system marks an academic year as active. `assigned_at` is server-set and not caller-controllable, so this is a correctness caveat rather than a security one; a promotion/rollover stage should make "current year" explicit instead.
- **The `list`-shadowing bug (ADR 0018/0019) has now hit four times**, this time in `timetable/service.py`. ADR 0019 said to revisit "if it recurs a third time"; it has. Going forward, `from __future__ import annotations` is the default for any new service or repository module in this codebase rather than a fix applied after each recurrence. A codebase-wide sweep of existing files was not done — those files work, and churning them has no payoff.
- The migration drops its enum type on downgrade (`DROP TYPE IF EXISTS day_of_week`), which autogenerate never emits. The codebase's earlier enum migrations have the same gap; left alone there rather than retro-fitting migrations whose downgrades have never been run.
- 608/608 tests passing, 36 of them for this stage — written to `docs/adr/0025`'s policy, with unit tests confined to the conflict rules and the `/timetable/me` resolution, and everything else integration-only.
