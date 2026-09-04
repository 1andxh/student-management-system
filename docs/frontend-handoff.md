# Frontend handoff — backend Stages 10–12

Covers everything added since the student PIN login work. Three of these are **breaking changes** to endpoints you may already be calling — those are first.

Full design rationale lives in `docs/adr/0022`–`0026`; this document is only what you need to integrate.

---

## 0. Get a populated database first

There is now a seed script. Run it once against an empty database:

```
docker compose exec api uv run python -m sms.scripts.seed_demo_data
```

It creates an academic year and term, 4 subjects, 4 teachers, 2 grade levels each with one section, 8 classes wired into a Monday timetable, 6 students assigned to sections (which auto-enrolls them into their section's classes), and one graded quiz per section.

It prints **all the logins once** — admin password, each teacher's password, each student's PIN. The API never returns these again, so copy them somewhere. Students log in at `POST /auth/login-pin` with `student_number` + `pin`; admin and teachers at `POST /auth/login` with email + password.

It refuses to run if the database already has grade levels, rather than half-seeding on top. Reset with `alembic downgrade base && alembic upgrade head`.

---

## 1. Breaking changes

### `GET /enrollments` now self-scopes for students
A `STUDENT` token previously saw **every enrollment in the school**. It now sees only its own. Passing another student's `student_id` is silently overridden with the caller's own — it does not error, it just returns their rows. `class_id` still narrows within their own enrollments.

`GET /enrollments/{id}` returns **404** for another student's enrollment (deliberately not 403 — a 403 would confirm the record exists).

Admin and teacher behaviour is unchanged, except that a teacher is now scoped to classes they teach.

### `GET /sections/{id}/students` is ADMIN + TEACHER only
A student calling it gets **403**. It was briefly open to any authenticated user; combined with `GET /classes` it let a student reconstruct which classmates were in which classes, which the point above exists to prevent.

### `GET /timetable` requires at least one filter
Calling it bare returns **422**. Pass at least one of `class_id`, `teacher_id`, `section_id`. Unfiltered it returned the whole school's schedule, which combined with the public `GET /classes` produced a staff location map.

If you want "my timetable", use `GET /timetable/me` instead — see below.

---

## 2. Teacher login

Teachers previously had no way to log in at all. Now:

```
POST /teachers/{teacher_id}/credentials        (ADMIN only)
```

No body. Returns **once**:

```json
{ "email": "ada.lovelace@demo.school", "password": "S_7lD50GYvsGVY0m3wErQw" }
```

Same one-time semantics as student PINs — it is never retrievable again, and calling the endpoint again issues a **new** password (so it doubles as a reset). The teacher then logs in through the existing `POST /auth/login` with email + password; there is no separate teacher login route.

**UI implication:** show the password once, in a modal or similar, and tell the admin to relay it. Don't build a screen that expects to fetch it later.

---

## 3. Teacher-facing views

```
GET /teachers/me            → the caller's own Teacher record  (existed already)
GET /teachers/me/classes    → the classes they teach           (new)
GET /timetable/me           → their own weekly schedule        (new)
```

`GET /classes` is still open to everyone and unfiltered — `/teachers/me/classes` is the convenience view, not a restriction.

---

## 4. Gradebook

```
GET /classes/{class_id}/gradebook       (ADMIN + TEACHER; 403 for students)
```

Returns the whole class assembled in one response rather than making you stitch `/assessments` and `/grades` together:

```json
{
  "class_id": "…",
  "assessments": [
    { "assessment_id": "…", "name": "Autumn Quiz 1", "type": "quiz",
      "max_score": "20.00", "date": "2025-10-03" }
  ],
  "students": [
    { "student_id": "…", "student_number": "STU-0003",
      "first_name": "Grace", "last_name": "Hopper",
      "scores": { "<assessment_id>": "12.00" } }
  ]
}
```

Notes for rendering:
- `assessments` is ordered **chronologically** — use it as your column order.
- `students` is ordered by `(last_name, first_name)`.
- `scores` is keyed by `assessment_id`, and every student has an entry for **every** assessment. An ungraded cell is `null`, never missing — so you can render the grid without null-checking for absent keys.
- Roster is **active enrollments only**. A dropped student disappears from this view even though their grades still exist.
- A teacher gets 403 for a class they don't teach. Admins can view any class.
- Students get 403 even for their own class — they use the existing self-scoped `GET /grades`.

---

## 5. Grade levels and sections (the K-12 model)

This is the biggest structural addition. Students now belong to a **grade level** and a **section** ("Grade 7, Section A"), rather than only being enrolled class by class.

```
POST|GET /grade-levels, GET|PATCH|DELETE /grade-levels/{id}      (ADMIN mutations)
POST|GET /sections,     GET|PATCH|DELETE /sections/{id}          (ADMIN mutations)
GET  /sections?grade_level_id=&academic_year_id=
GET  /sections/{id}/students                                     (ADMIN + TEACHER)
POST|DELETE /sections/{section_id}/students/{student_id}         (ADMIN)
POST|DELETE /sections/{section_id}/classes/{class_id}            (ADMIN)
```

**The behaviour that matters most:** assigning a student to a section **auto-creates their enrollments** for every class attached to that section. You do not enroll them class by class. Likewise, attaching a class to a populated section back-fills enrollments for everyone already in it.

Other rules worth knowing before you build the admin screens:
- A student can be in **one section per academic year**. Assigning them to a second in the same year → 409.
- Section names are unique per `(grade_level, academic_year)` — so "A" can exist in Grade 7 and Grade 8, and in different years.
- A class can only be attached to **one** section. Re-attaching to another → 409; detach first.
- The class's term must be in the **same academic year** as the section → 409 otherwise.
- Once a class is attached to a section, its `term_id` is pinned; `PATCH /classes` changing it → 409. Detach first.
- Section capacity is enforced on assignment → 409 when full.
- Detaching a class or unassigning a student **leaves existing enrollments intact** — that's academic-record data, removed explicitly through the enrollments API if you actually want it gone.

`ClassRead` gained `section_id` (read-only — set only through the attach/detach routes above, not through `ClassCreate`/`ClassUpdate`).

---

## 6. Timetable

```
POST|GET /periods, GET|PATCH|DELETE /periods/{id}     (ADMIN mutations)
POST /timetable/slots                                 (ADMIN)
DELETE /timetable/slots/{slot_id}                     (ADMIN)
GET  /timetable?class_id=&teacher_id=&section_id=&day_of_week=
GET  /timetable/me
```

`Period` is the school's bell schedule (`name`, `start_time`, `end_time`) — defined once, school-wide. A `ScheduleSlot` is one weekly recurring meeting: `(class_id, day_of_week, period_id)`. `day_of_week` is `monday`…`friday`.

There is no date on a slot — it's a repeating weekly pattern, not a calendar occurrence.

**Conflict rules**, each with its own 409 so you can show a useful message:
- `TeacherDoubleBookedError` — that teacher already has a class in that day/period
- `RoomDoubleBookedError` — that room is taken (matched on `Class.room`, which is free text; a class with no room set never conflicts)
- `SectionDoubleBookedError` — that section already has a class then

Also: **periods may not overlap in time** → 409. Back-to-back periods (one ending 09:45, the next starting 09:45) are fine. Deleting a period still used by a slot → 409.

`GET /timetable/me` returns a teacher's own classes' slots, or a student's own section's slots. Admins get an empty list — they have no personal timetable, so use the filters.

---

## 7. Known limitations, so you don't design around them

- **Timetable conflicts are only checked when a slot is created.** Changing a class's teacher or room afterwards via `PATCH /classes` can create a conflict silently. Don't build UI that assumes the timetable is always conflict-free.
- **Rooms are free text on `Class`, not entities.** "Lab 2" and "lab 2" are different rooms to the conflict checker.
- **No password self-service.** Nobody can change their own password; admins issue and reissue. There is no email infrastructure, so no reset links and no notifications.
- **No promotion / year rollover.** Nothing advances a student to the next grade level, and `enrollment_status: "graduated"` is never produced automatically.
- **"Current section" means most recent assignment.** Nothing marks an academic year as active yet.
- **Rate limiting is per-IP, not per-account** — 5/minute on both login routes.
