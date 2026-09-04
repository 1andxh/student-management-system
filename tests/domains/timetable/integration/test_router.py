from collections.abc import Awaitable, Callable
from datetime import date, time
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from sms.domains.academic_years.models import AcademicYear, Term
from sms.domains.classes.models import Class, Subject
from sms.domains.teachers.models import Teacher
from sms.domains.timetable.models import DayOfWeek, Period
from sms.domains.users.models import User, UserRole


def make_period_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": f"Period {uuid4().hex[:8]}",
        "start_time": "08:00:00",
        "end_time": "08:45:00",
    }
    payload.update(overrides)
    return payload


def make_slot_payload(class_id: object, period_id: object, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "class_id": str(class_id),
        "day_of_week": DayOfWeek.MONDAY.value,
        "period_id": str(period_id),
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# local factory fixtures — Subject/AcademicYear/Term/Teacher/Class chain,
# mirroring tests/domains/enrollments/integration/test_router.py's identical
# local copies (neither file's fixtures are shared to conftest.py, same
# convention). Period is new to this domain.
# ---------------------------------------------------------------------------


@pytest.fixture
def make_subject(db_session: AsyncSession):
    async def _make_subject(**overrides: object) -> Subject:
        unique = uuid4().hex[:8]
        defaults: dict[str, object] = {"name": f"Subject {unique}", "code": f"C{unique}"}
        defaults.update(overrides)
        subject = Subject(**defaults)
        db_session.add(subject)
        await db_session.commit()
        await db_session.refresh(subject)
        return subject

    return _make_subject


@pytest.fixture
def make_academic_year(db_session: AsyncSession):
    async def _make_academic_year(**overrides: object) -> AcademicYear:
        defaults: dict[str, object] = {
            "name": f"Year {uuid4().hex[:8]}",
            "start_date": date(2024, 9, 1),
            "end_date": date(2025, 6, 30),
        }
        defaults.update(overrides)
        year = AcademicYear(**defaults)
        db_session.add(year)
        await db_session.commit()
        await db_session.refresh(year)
        return year

    return _make_academic_year


@pytest.fixture
def make_term(
    db_session: AsyncSession, make_academic_year: Callable[..., Awaitable[AcademicYear]]
):
    async def _make_term(**overrides: object) -> Term:
        if "academic_year_id" not in overrides:
            year = await make_academic_year()
            overrides = {**overrides, "academic_year_id": year.id}
        defaults: dict[str, object] = {
            "name": "Term 1",
            "start_date": date(2024, 9, 1),
            "end_date": date(2024, 12, 20),
        }
        defaults.update(overrides)
        term = Term(**defaults)
        db_session.add(term)
        await db_session.commit()
        await db_session.refresh(term)
        return term

    return _make_term


@pytest.fixture
def make_teacher(db_session: AsyncSession):
    async def _make_teacher(**overrides: object) -> Teacher:
        unique = uuid4().hex[:8]
        defaults: dict[str, object] = {
            "first_name": "Grace",
            "last_name": "Hopper",
            "email": f"teacher{unique}@example.com",
            "hire_date": date(2015, 6, 1),
        }
        defaults.update(overrides)
        teacher = Teacher(**defaults)
        db_session.add(teacher)
        await db_session.commit()
        await db_session.refresh(teacher)
        return teacher

    return _make_teacher


@pytest.fixture
def make_class(
    db_session: AsyncSession,
    make_subject: Callable[..., Awaitable[Subject]],
    make_term: Callable[..., Awaitable[Term]],
    make_teacher: Callable[..., Awaitable[Teacher]],
):
    """Unlike other domains' make_class, this one builds its own
    Subject/Term/Teacher when not supplied — timetable tests care about
    Class.teacher_id/room/section_id, not the academic scaffolding around
    it, so most call sites only need to pass the field(s) relevant to the
    conflict rule under test."""

    async def _make_class(**overrides: object) -> Class:
        if "subject_id" not in overrides:
            subject = await make_subject()
            overrides = {**overrides, "subject_id": subject.id}
        if "term_id" not in overrides:
            term = await make_term()
            overrides = {**overrides, "term_id": term.id}
        if "teacher_id" not in overrides:
            teacher = await make_teacher()
            overrides = {**overrides, "teacher_id": teacher.id}
        defaults: dict[str, object] = {"capacity": 30, "room": None}
        defaults.update(overrides)
        klass = Class(**defaults)
        db_session.add(klass)
        await db_session.commit()
        await db_session.refresh(klass)
        return klass

    return _make_class


@pytest.fixture
def make_period(db_session: AsyncSession):
    async def _make_period(**overrides: object) -> Period:
        unique = uuid4().hex[:8]
        defaults: dict[str, object] = {
            "name": f"Period {unique}",
            "start_time": time(8, 0),
            "end_time": time(8, 45),
        }
        defaults.update(overrides)
        period = Period(**defaults)
        db_session.add(period)
        await db_session.commit()
        await db_session.refresh(period)
        return period

    return _make_period


@pytest.fixture
def make_manage_headers(
    make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
):
    """Auth header for a user with the given role — admin by default.
    Periods/slot mutations are ADMIN-only, same tier as Classes/Teachers
    (docs/adr/0016)."""

    async def _make_headers(role: UserRole = UserRole.ADMIN, **overrides: object) -> dict[str, str]:
        user = await make_user(role=role, **overrides)
        return auth_headers(user)

    return _make_headers


# ---------------------------------------------------------------------------
# /periods
# ---------------------------------------------------------------------------


async def test_post_periods_happy_path(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin-period-1@example.com")

    response = await client.post(
        "/periods", json=make_period_payload(name="Period 1"), headers=headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Period 1"
    assert body["start_time"] == "08:00:00"
    assert body["end_time"] == "08:45:00"
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


async def test_get_period_happy_path(
    client: AsyncClient,
    make_period: Callable[..., Awaitable[Period]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    period = await make_period(name="Period Get")
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher-period-get@example.com")

    response = await client.get(f"/periods/{period.id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == str(period.id)


async def test_get_period_nonexistent_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher-period-404@example.com")

    response = await client.get(f"/periods/{uuid4()}", headers=headers)

    assert response.status_code == 404


async def test_get_periods_list_ordered_by_start_time(
    client: AsyncClient,
    make_period: Callable[..., Awaitable[Period]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    await make_period(name="Afternoon", start_time=time(13, 0), end_time=time(13, 45))
    await make_period(name="Morning", start_time=time(8, 0), end_time=time(8, 45))
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher-period-list@example.com")

    response = await client.get("/periods", headers=headers)

    assert response.status_code == 200
    body = response.json()
    names = [p["name"] for p in body if p["name"] in {"Afternoon", "Morning"}]
    assert names == ["Morning", "Afternoon"]


async def test_patch_period_happy_path(
    client: AsyncClient,
    make_period: Callable[..., Awaitable[Period]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    period = await make_period(name="Before Rename")
    headers = await make_manage_headers(email="admin-period-patch@example.com")

    response = await client.patch(
        f"/periods/{period.id}", json={"name": "After Rename"}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["name"] == "After Rename"


async def test_delete_period_happy_path(
    client: AsyncClient,
    make_period: Callable[..., Awaitable[Period]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    period = await make_period(name="To Delete")
    headers = await make_manage_headers(email="admin-period-delete@example.com")

    response = await client.delete(f"/periods/{period.id}", headers=headers)
    assert response.status_code == 204

    follow_up = await client.get(f"/periods/{period.id}", headers=headers)
    assert follow_up.status_code == 404


async def test_post_periods_duplicate_name_returns_409(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin-period-dup@example.com")
    await client.post("/periods", json=make_period_payload(name="Dup Period"), headers=headers)

    response = await client.post(
        "/periods", json=make_period_payload(name="Dup Period"), headers=headers
    )

    assert response.status_code == 409


async def test_post_periods_end_before_start_returns_422(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin-period-422@example.com")

    response = await client.post(
        "/periods",
        json=make_period_payload(start_time="09:00:00", end_time="09:00:00"),
        headers=headers,
    )

    assert response.status_code == 422


async def test_post_periods_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.post("/periods", json=make_period_payload())

    assert response.status_code == 401


async def test_post_periods_as_teacher_role_returns_403(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher-period-403@example.com")

    response = await client.post("/periods", json=make_period_payload(), headers=headers)

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# /timetable/slots
# ---------------------------------------------------------------------------


async def test_post_slots_happy_path(
    client: AsyncClient,
    make_class: Callable[..., Awaitable[Class]],
    make_period: Callable[..., Awaitable[Period]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    klass = await make_class()
    period = await make_period()
    headers = await make_manage_headers(email="admin-slot-1@example.com")

    response = await client.post(
        "/timetable/slots", json=make_slot_payload(klass.id, period.id), headers=headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["class_id"] == str(klass.id)
    assert body["period_id"] == str(period.id)
    assert body["day_of_week"] == "monday"
    assert "id" in body
    assert "created_at" in body


async def test_post_slots_nonexistent_class_returns_404(
    client: AsyncClient,
    make_period: Callable[..., Awaitable[Period]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    period = await make_period()
    headers = await make_manage_headers(email="admin-slot-404-class@example.com")

    response = await client.post(
        "/timetable/slots", json=make_slot_payload(uuid4(), period.id), headers=headers
    )

    assert response.status_code == 404


async def test_post_slots_nonexistent_period_returns_404(
    client: AsyncClient,
    make_class: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    klass = await make_class()
    headers = await make_manage_headers(email="admin-slot-404-period@example.com")

    response = await client.post(
        "/timetable/slots", json=make_slot_payload(klass.id, uuid4()), headers=headers
    )

    assert response.status_code == 404


async def test_post_slots_conflict_returns_409(
    client: AsyncClient,
    make_class: Callable[..., Awaitable[Class]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_period: Callable[..., Awaitable[Period]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    """One conflict rule (teacher double-booked) proven end-to-end over
    HTTP — proof the service's conflict check is actually wired into the
    route, not a re-test of all three rules (those are unit-tested
    exhaustively in tests/domains/timetable/unit/test_service.py)."""
    teacher = await make_teacher()
    first_class = await make_class(teacher_id=teacher.id)
    second_class = await make_class(teacher_id=teacher.id)
    period = await make_period()
    headers = await make_manage_headers(email="admin-slot-conflict@example.com")
    await client.post(
        "/timetable/slots", json=make_slot_payload(first_class.id, period.id), headers=headers
    )

    response = await client.post(
        "/timetable/slots", json=make_slot_payload(second_class.id, period.id), headers=headers
    )

    assert response.status_code == 409


async def test_delete_slot_happy_path(
    client: AsyncClient,
    make_class: Callable[..., Awaitable[Class]],
    make_period: Callable[..., Awaitable[Period]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    klass = await make_class()
    period = await make_period()
    headers = await make_manage_headers(email="admin-slot-delete@example.com")
    created = await client.post(
        "/timetable/slots", json=make_slot_payload(klass.id, period.id), headers=headers
    )
    slot_id = created.json()["id"]

    response = await client.delete(f"/timetable/slots/{slot_id}", headers=headers)
    assert response.status_code == 204

    listing = await client.get("/timetable", params={"class_id": str(klass.id)}, headers=headers)
    assert listing.json() == []


async def test_delete_slot_nonexistent_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin-slot-delete-404@example.com")

    response = await client.delete(f"/timetable/slots/{uuid4()}", headers=headers)

    assert response.status_code == 404


async def test_post_slots_without_token_returns_401(
    client: AsyncClient,
    make_class: Callable[..., Awaitable[Class]],
    make_period: Callable[..., Awaitable[Period]],
) -> None:
    klass = await make_class()
    period = await make_period()

    response = await client.post("/timetable/slots", json=make_slot_payload(klass.id, period.id))

    assert response.status_code == 401


async def test_post_slots_as_teacher_role_returns_403(
    client: AsyncClient,
    make_class: Callable[..., Awaitable[Class]],
    make_period: Callable[..., Awaitable[Period]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    klass = await make_class()
    period = await make_period()
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher-slot-403@example.com")

    response = await client.post(
        "/timetable/slots", json=make_slot_payload(klass.id, period.id), headers=headers
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET /timetable, GET /timetable/me
# ---------------------------------------------------------------------------


async def test_get_timetable_filtered_by_class_id(
    client: AsyncClient,
    make_class: Callable[..., Awaitable[Class]],
    make_period: Callable[..., Awaitable[Period]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    wanted_class = await make_class()
    other_class = await make_class()
    period = await make_period()
    headers = await make_manage_headers(email="admin-timetable-filter-class@example.com")
    await client.post(
        "/timetable/slots", json=make_slot_payload(wanted_class.id, period.id), headers=headers
    )
    await client.post(
        "/timetable/slots",
        json=make_slot_payload(other_class.id, period.id, day_of_week=DayOfWeek.TUESDAY.value),
        headers=headers,
    )

    response = await client.get(
        "/timetable", params={"class_id": str(wanted_class.id)}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["class_id"] == str(wanted_class.id)


async def test_get_timetable_filtered_by_teacher_id(
    client: AsyncClient,
    make_class: Callable[..., Awaitable[Class]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_period: Callable[..., Awaitable[Period]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    wanted_teacher = await make_teacher()
    wanted_class = await make_class(teacher_id=wanted_teacher.id)
    other_class = await make_class()
    period = await make_period()
    headers = await make_manage_headers(email="admin-timetable-filter-teacher@example.com")
    await client.post(
        "/timetable/slots", json=make_slot_payload(wanted_class.id, period.id), headers=headers
    )
    await client.post(
        "/timetable/slots",
        json=make_slot_payload(other_class.id, period.id, day_of_week=DayOfWeek.TUESDAY.value),
        headers=headers,
    )

    response = await client.get(
        "/timetable", params={"teacher_id": str(wanted_teacher.id)}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["class_id"] == str(wanted_class.id)


async def test_get_timetable_me_as_teacher(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[User], dict[str, str]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_class: Callable[..., Awaitable[Class]],
    make_period: Callable[..., Awaitable[Period]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    teacher_user = await make_user(role=UserRole.TEACHER, email="teacher-me@example.com")
    teacher = await make_teacher(user_id=teacher_user.id, email="teacher-me-record@example.com")
    my_class = await make_class(teacher_id=teacher.id)
    other_class = await make_class()
    period = await make_period()
    admin_headers = await make_manage_headers(email="admin-timetable-me@example.com")
    await client.post(
        "/timetable/slots", json=make_slot_payload(my_class.id, period.id), headers=admin_headers
    )
    await client.post(
        "/timetable/slots",
        json=make_slot_payload(other_class.id, period.id, day_of_week=DayOfWeek.TUESDAY.value),
        headers=admin_headers,
    )

    response = await client.get("/timetable/me", headers=auth_headers(teacher_user))

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["class_id"] == str(my_class.id)


# ---------------------------------------------------------------------------
# security-auditor findings
# ---------------------------------------------------------------------------


async def test_post_periods_overlapping_times_returns_409(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    # Without this, every conflict rule is bypassable: the rules key on
    # period_id, so two periods covering the same clock time let the same
    # teacher, room and section be booked twice over. Enforced by the
    # ex_periods_no_overlap exclusion constraint.
    headers = await make_manage_headers(email="admin-overlap@example.com")
    first = await client.post(
        "/periods",
        json=make_period_payload(start_time="10:00:00", end_time="10:45:00"),
        headers=headers,
    )
    assert first.status_code == 201

    response = await client.post(
        "/periods",
        json=make_period_payload(start_time="10:15:00", end_time="10:30:00"),
        headers=headers,
    )

    assert response.status_code == 409


async def test_post_periods_adjacent_times_do_not_overlap(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    # A period ending exactly when the next begins must still be allowed —
    # tsrange is half-open, so back-to-back periods don't overlap. Guards
    # against the constraint being written with an inclusive range.
    headers = await make_manage_headers(email="admin-adjacent@example.com")
    first = await client.post(
        "/periods",
        json=make_period_payload(start_time="09:00:00", end_time="09:45:00"),
        headers=headers,
    )
    assert first.status_code == 201

    response = await client.post(
        "/periods",
        json=make_period_payload(start_time="09:45:00", end_time="10:30:00"),
        headers=headers,
    )

    assert response.status_code == 201


async def test_get_timetable_without_any_filter_returns_422(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    # An unfiltered read returned the whole school's schedule unpaginated.
    headers = await make_manage_headers(email="admin-nofilter@example.com")

    response = await client.get("/timetable", headers=headers)

    assert response.status_code == 422


async def test_patch_period_end_before_start_returns_422(
    client: AsyncClient,
    make_period: Callable[..., Awaitable[Period]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    # A partial PATCH can only be validated against the stored row, so the
    # schema can't catch this — the service previously raised a bare
    # ValueError, which surfaced as a 500 for an ordinary user typo.
    period = await make_period(start_time=time(8, 0), end_time=time(8, 45))
    headers = await make_manage_headers(email="admin-badtimes@example.com")

    response = await client.patch(
        f"/periods/{period.id}", json={"end_time": "07:00:00"}, headers=headers
    )

    assert response.status_code == 422


async def test_delete_period_still_scheduled_returns_409(
    client: AsyncClient,
    make_class: Callable[..., Awaitable[Class]],
    make_period: Callable[..., Awaitable[Period]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    # schedule_slots.period_id is RESTRICT — this previously surfaced as a
    # 500 rather than a conflict.
    klass = await make_class()
    period = await make_period()
    headers = await make_manage_headers(email="admin-periodinuse@example.com")
    created = await client.post(
        "/timetable/slots", json=make_slot_payload(klass.id, period.id), headers=headers
    )
    assert created.status_code == 201

    response = await client.delete(f"/periods/{period.id}", headers=headers)

    assert response.status_code == 409
