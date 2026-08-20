from collections.abc import Awaitable, Callable
from datetime import date
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from sms.domains.academic_years.models import AcademicYear, Term
from sms.domains.classes.models import Class, Subject
from sms.domains.students.models import Student
from sms.domains.teachers.models import Teacher
from sms.domains.users.models import User, UserRole


def make_enrollment_payload(student_id: object, class_id: object, **overrides: object) -> dict:
    payload: dict[str, object] = {"student_id": str(student_id), "class_id": str(class_id)}
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# local factory fixtures — Student and the Subject/Term/Teacher/Class chain,
# mirroring tests/domains/students/integration/test_router.py and
# tests/domains/classes/integration/test_router.py respectively (neither
# file's fixtures are shared to conftest.py yet, so enrollments keeps its
# own local copies, same convention).
# ---------------------------------------------------------------------------


@pytest.fixture
def make_student(db_session: AsyncSession):
    async def _make_student(**overrides: object) -> Student:
        unique = uuid4().hex[:8]
        defaults: dict[str, object] = {
            "student_number": f"S-{unique}",
            "first_name": "Grace",
            "last_name": "Hopper",
            "date_of_birth": date(1906, 12, 9),
            "email": f"{unique}@example.com",
            "guardian_name": "Walter Hopper",
            "guardian_phone": "+1-555-0200",
        }
        defaults.update(overrides)
        student = Student(**defaults)
        db_session.add(student)
        await db_session.commit()
        await db_session.refresh(student)
        return student

    return _make_student


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
        # name has a uniqueness constraint (uq_academic_years_name) — tests
        # that build more than one class (e.g. list-filter tests) go through
        # this fixture more than once, so the default must be unique per
        # call, not a fixed literal.
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
def make_class(db_session: AsyncSession):
    async def _make_class(
        subject_id: object, term_id: object, teacher_id: object, **overrides: object
    ) -> Class:
        defaults: dict[str, object] = {
            "subject_id": subject_id,
            "term_id": term_id,
            "teacher_id": teacher_id,
            "capacity": 30,
            "room": "Room 101",
        }
        defaults.update(overrides)
        klass = Class(**defaults)
        db_session.add(klass)
        await db_session.commit()
        await db_session.refresh(klass)
        return klass

    return _make_class


@pytest.fixture
def make_enrollable_class(
    make_subject: Callable[..., Awaitable[Subject]],
    make_term: Callable[..., Awaitable[Term]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_class: Callable[..., Awaitable[Class]],
):
    """Convenience wrapper — most enrollment tests just need *a* class with
    a given capacity and don't care about its Subject/Term/Teacher, so this
    builds the whole chain in one call (each with unique identifying
    fields, so it's safe to call more than once per test)."""

    async def _make(capacity: int = 30, **overrides: object) -> Class:
        subject = await make_subject()
        term = await make_term()
        teacher = await make_teacher()
        return await make_class(subject.id, term.id, teacher.id, capacity=capacity, **overrides)

    return _make


@pytest.fixture
def make_manage_headers(
    make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
):
    """Auth header for a user with the given role — admin by default, since
    both ADMIN and TEACHER are allowed to enroll/drop; pass
    role=UserRole.STUDENT to exercise the "authenticated but not allowed to
    mutate" path instead."""

    async def _make_headers(role: UserRole = UserRole.ADMIN, **overrides: object) -> dict[str, str]:
        user = await make_user(role=role, **overrides)
        return auth_headers(user)

    return _make_headers


# ---------------------------------------------------------------------------
# POST /enrollments
# ---------------------------------------------------------------------------


async def test_post_enrollments_happy_path(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_enrollable_class: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    student = await make_student()
    klass = await make_enrollable_class()
    headers = await make_manage_headers(email="admin1@example.com")

    response = await client.post(
        "/enrollments", json=make_enrollment_payload(student.id, klass.id), headers=headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["student_id"] == str(student.id)
    assert body["class_id"] == str(klass.id)
    assert body["status"] == "active"
    assert "id" in body
    assert "enrolled_at" in body


async def test_post_enrollments_class_at_capacity_returns_409(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_enrollable_class: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    klass = await make_enrollable_class(capacity=1)
    first_student = await make_student()
    second_student = await make_student()
    headers = await make_manage_headers(email="admin2@example.com")

    await client.post(
        "/enrollments",
        json=make_enrollment_payload(first_student.id, klass.id),
        headers=headers,
    )
    response = await client.post(
        "/enrollments",
        json=make_enrollment_payload(second_student.id, klass.id),
        headers=headers,
    )

    assert response.status_code == 409


async def test_post_enrollments_duplicate_returns_409(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_enrollable_class: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    student = await make_student()
    klass = await make_enrollable_class()
    headers = await make_manage_headers(email="admin3@example.com")

    await client.post(
        "/enrollments", json=make_enrollment_payload(student.id, klass.id), headers=headers
    )
    response = await client.post(
        "/enrollments", json=make_enrollment_payload(student.id, klass.id), headers=headers
    )

    assert response.status_code == 409


async def test_post_enrollments_nonexistent_student_returns_404(
    client: AsyncClient,
    make_enrollable_class: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    klass = await make_enrollable_class()
    headers = await make_manage_headers(email="admin4@example.com")

    response = await client.post(
        "/enrollments", json=make_enrollment_payload(uuid4(), klass.id), headers=headers
    )

    assert response.status_code == 404


async def test_post_enrollments_nonexistent_class_returns_404(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    student = await make_student()
    headers = await make_manage_headers(email="admin5@example.com")

    response = await client.post(
        "/enrollments", json=make_enrollment_payload(student.id, uuid4()), headers=headers
    )

    assert response.status_code == 404


async def test_post_enrollments_without_token_returns_401(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_enrollable_class: Callable[..., Awaitable[Class]],
) -> None:
    student = await make_student()
    klass = await make_enrollable_class()

    response = await client.post(
        "/enrollments", json=make_enrollment_payload(student.id, klass.id)
    )

    assert response.status_code == 401


async def test_post_enrollments_as_student_role_returns_403(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_enrollable_class: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    student = await make_student()
    klass = await make_enrollable_class()
    headers = await make_manage_headers(role=UserRole.STUDENT, email="student1@example.com")

    response = await client.post(
        "/enrollments", json=make_enrollment_payload(student.id, klass.id), headers=headers
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET /enrollments
# ---------------------------------------------------------------------------


async def test_get_enrollments_list_no_filters(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_enrollable_class: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    class_a = await make_enrollable_class()
    class_b = await make_enrollable_class()
    student_a = await make_student()
    student_b = await make_student()
    headers = await make_manage_headers(email="admin6@example.com")
    await client.post(
        "/enrollments", json=make_enrollment_payload(student_a.id, class_a.id), headers=headers
    )
    await client.post(
        "/enrollments", json=make_enrollment_payload(student_b.id, class_b.id), headers=headers
    )

    response = await client.get("/enrollments", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 2


async def test_get_enrollments_list_filtered_by_student_id(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_enrollable_class: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    class_a = await make_enrollable_class()
    class_b = await make_enrollable_class()
    student_a = await make_student()
    student_b = await make_student()
    headers = await make_manage_headers(email="admin7@example.com")
    await client.post(
        "/enrollments", json=make_enrollment_payload(student_a.id, class_a.id), headers=headers
    )
    await client.post(
        "/enrollments", json=make_enrollment_payload(student_a.id, class_b.id), headers=headers
    )
    await client.post(
        "/enrollments", json=make_enrollment_payload(student_b.id, class_a.id), headers=headers
    )

    response = await client.get(
        "/enrollments", params={"student_id": str(student_a.id)}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert {e["student_id"] for e in body} == {str(student_a.id)}


async def test_get_enrollments_list_filtered_by_class_id(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_enrollable_class: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    class_a = await make_enrollable_class()
    class_b = await make_enrollable_class()
    student_a = await make_student()
    student_b = await make_student()
    headers = await make_manage_headers(email="admin8@example.com")
    await client.post(
        "/enrollments", json=make_enrollment_payload(student_a.id, class_a.id), headers=headers
    )
    await client.post(
        "/enrollments", json=make_enrollment_payload(student_b.id, class_a.id), headers=headers
    )
    await client.post(
        "/enrollments", json=make_enrollment_payload(student_a.id, class_b.id), headers=headers
    )

    response = await client.get(
        "/enrollments", params={"class_id": str(class_a.id)}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert {e["class_id"] for e in body} == {str(class_a.id)}


async def test_get_enrollments_list_pagination_smoke(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_enrollable_class: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    headers = await make_manage_headers(email="admin-pg-smoke@example.com")
    for _ in range(3):
        student = await make_student()
        klass = await make_enrollable_class()
        await client.post(
            "/enrollments", json=make_enrollment_payload(student.id, klass.id), headers=headers
        )

    response = await client.get("/enrollments", params={"limit": 2, "offset": 0}, headers=headers)

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.headers["X-Total-Count"] == "3"


async def test_get_enrollments_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/enrollments")

    assert response.status_code == 401


async def test_get_enrollment_by_id_happy_path(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_enrollable_class: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    student = await make_student()
    klass = await make_enrollable_class()
    headers = await make_manage_headers(email="admin9@example.com")
    created = await client.post(
        "/enrollments", json=make_enrollment_payload(student.id, klass.id), headers=headers
    )
    enrollment_id = created.json()["id"]

    response = await client.get(f"/enrollments/{enrollment_id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == enrollment_id
    assert body["student_id"] == str(student.id)


async def test_get_enrollment_by_id_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin10@example.com")

    response = await client.get(f"/enrollments/{uuid4()}", headers=headers)

    assert response.status_code == 404
    assert "detail" in response.json()


# ---------------------------------------------------------------------------
# PATCH /enrollments/{id}/drop
# ---------------------------------------------------------------------------


async def test_patch_drop_enrollment_happy_path(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_enrollable_class: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    student = await make_student()
    klass = await make_enrollable_class()
    headers = await make_manage_headers(email="admin11@example.com")
    created = await client.post(
        "/enrollments", json=make_enrollment_payload(student.id, klass.id), headers=headers
    )
    enrollment_id = created.json()["id"]

    response = await client.patch(f"/enrollments/{enrollment_id}/drop", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == enrollment_id
    assert body["status"] == "dropped"


async def test_patch_drop_enrollment_already_dropped_returns_409(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_enrollable_class: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    student = await make_student()
    klass = await make_enrollable_class()
    headers = await make_manage_headers(email="admin12@example.com")
    created = await client.post(
        "/enrollments", json=make_enrollment_payload(student.id, klass.id), headers=headers
    )
    enrollment_id = created.json()["id"]
    await client.patch(f"/enrollments/{enrollment_id}/drop", headers=headers)

    response = await client.patch(f"/enrollments/{enrollment_id}/drop", headers=headers)

    assert response.status_code == 409


async def test_patch_drop_enrollment_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin13@example.com")

    response = await client.patch(f"/enrollments/{uuid4()}/drop", headers=headers)

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_patch_drop_enrollment_as_student_role_returns_403(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_enrollable_class: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    student = await make_student()
    klass = await make_enrollable_class()
    admin_headers = await make_manage_headers(email="admin14@example.com")
    created = await client.post(
        "/enrollments",
        json=make_enrollment_payload(student.id, klass.id),
        headers=admin_headers,
    )
    enrollment_id = created.json()["id"]
    student_headers = await make_manage_headers(
        role=UserRole.STUDENT, email="student2@example.com"
    )

    response = await client.patch(
        f"/enrollments/{enrollment_id}/drop", headers=student_headers
    )

    assert response.status_code == 403
