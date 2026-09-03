from collections.abc import Awaitable, Callable
from datetime import date
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from sms.domains.academic_years.models import AcademicYear, Term
from sms.domains.classes.models import Class, Subject
from sms.domains.sections.models import GradeLevel, Section
from sms.domains.students.models import Student
from sms.domains.teachers.models import Teacher
from sms.domains.users.models import User, UserRole


def make_grade_level_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {"name": "Grade 1", "rank": 1}
    payload.update(overrides)
    return payload


def make_section_payload(grade_level_id: object, academic_year_id: object, **overrides: object) -> dict:
    payload: dict[str, object] = {
        "grade_level_id": str(grade_level_id),
        "academic_year_id": str(academic_year_id),
        "name": "Section A",
        "capacity": 30,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# local factory fixtures — same "direct DB insert" convention as
# tests/domains/enrollments/integration/test_router.py and
# tests/domains/classes/integration/test_router.py; none of these are
# shared to conftest.py yet, so sections keeps its own local copies.
# ---------------------------------------------------------------------------


@pytest.fixture
def make_grade_level(db_session: AsyncSession):
    async def _make_grade_level(**overrides: object) -> GradeLevel:
        unique = uuid4().hex[:8]
        defaults: dict[str, object] = {"name": f"Grade {unique}", "rank": 1}
        defaults.update(overrides)
        grade_level = GradeLevel(**defaults)
        db_session.add(grade_level)
        await db_session.commit()
        await db_session.refresh(grade_level)
        return grade_level

    return _make_grade_level


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
def make_section(db_session: AsyncSession):
    async def _make_section(grade_level_id: object, academic_year_id: object, **overrides: object) -> Section:
        unique = uuid4().hex[:8]
        defaults: dict[str, object] = {
            "grade_level_id": grade_level_id,
            "academic_year_id": academic_year_id,
            "name": f"Section {unique}",
            "capacity": 30,
        }
        defaults.update(overrides)
        section = Section(**defaults)
        db_session.add(section)
        await db_session.commit()
        await db_session.refresh(section)
        return section

    return _make_section


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
def make_term(db_session: AsyncSession, make_academic_year: Callable[..., Awaitable[AcademicYear]]):
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
def make_class(db_session: AsyncSession):
    async def _make_class(subject_id: object, term_id: object, teacher_id: object, **overrides: object) -> Class:
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
def make_classable(
    make_subject: Callable[..., Awaitable[Subject]],
    make_term: Callable[..., Awaitable[object]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_class: Callable[..., Awaitable[Class]],
):
    """Convenience wrapper building the whole Subject/Term/Teacher/Class
    chain — most section-attach tests just need *a* class and don't care
    about its Subject/Term/Teacher. Mirrors
    tests/domains/enrollments/integration/test_router.py's
    make_enrollable_class.

    `academic_year_id` matters: attach_class rejects a class whose term
    belongs to a different academic year than the section, so any test
    attaching this class must pass the section's own year here."""

    async def _make(
        capacity: int = 30, academic_year_id: object | None = None, **overrides: object
    ) -> Class:
        subject = await make_subject()
        term = (
            await make_term(academic_year_id=academic_year_id)
            if academic_year_id is not None
            else await make_term()
        )
        teacher = await make_teacher()
        return await make_class(subject.id, term.id, teacher.id, capacity=capacity, **overrides)

    return _make


@pytest.fixture
def make_manage_headers(
    make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
):
    """Auth header for a user with the given role — admin by default, since
    grade-levels/sections mutations are ADMIN-only (same tier as
    subjects/classes/academic-years)."""

    async def _make_headers(role: UserRole = UserRole.ADMIN, **overrides: object) -> dict[str, str]:
        user = await make_user(role=role, **overrides)
        return auth_headers(user)

    return _make_headers


# ---------------------------------------------------------------------------
# /grade-levels
# ---------------------------------------------------------------------------


async def test_post_grade_levels_happy_path(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin-gl1@example.com")

    response = await client.post("/grade-levels", json=make_grade_level_payload(), headers=headers)

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Grade 1"
    assert body["rank"] == 1
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


async def test_post_grade_levels_rank_zero_accepted(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin-gl2@example.com")

    response = await client.post(
        "/grade-levels", json=make_grade_level_payload(name="Kindergarten", rank=0), headers=headers
    )

    assert response.status_code == 201
    assert response.json()["rank"] == 0


async def test_post_grade_levels_negative_rank_returns_422(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin-gl3@example.com")

    response = await client.post(
        "/grade-levels", json=make_grade_level_payload(rank=-1), headers=headers
    )

    assert response.status_code == 422


async def test_post_grade_levels_duplicate_name_returns_409(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin-gl4@example.com")
    await client.post(
        "/grade-levels", json=make_grade_level_payload(name="Dup", rank=1), headers=headers
    )

    response = await client.post(
        "/grade-levels", json=make_grade_level_payload(name="Dup", rank=2), headers=headers
    )

    assert response.status_code == 409


async def test_post_grade_levels_duplicate_rank_returns_409(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin-gl5@example.com")
    await client.post(
        "/grade-levels", json=make_grade_level_payload(name="A", rank=9), headers=headers
    )

    response = await client.post(
        "/grade-levels", json=make_grade_level_payload(name="B", rank=9), headers=headers
    )

    assert response.status_code == 409


async def test_post_grade_levels_as_teacher_role_returns_403(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher-gl1@example.com")

    response = await client.post("/grade-levels", json=make_grade_level_payload(), headers=headers)

    assert response.status_code == 403


async def test_get_grade_levels_list(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    await make_grade_level(name="Grade A", rank=1)
    await make_grade_level(name="Grade B", rank=2)
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher-gl2@example.com")

    response = await client.get("/grade-levels", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 2


async def test_get_grade_levels_list_pagination_smoke(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    for i in range(3):
        await make_grade_level(name=f"Grade PG {i}", rank=100 + i)
    headers = await make_manage_headers(email="admin-gl-pg@example.com")

    response = await client.get("/grade-levels", params={"limit": 2, "offset": 0}, headers=headers)

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.headers["X-Total-Count"] == "3"


async def test_get_grade_level_by_id_happy_path(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    headers = await make_manage_headers(email="admin-gl6@example.com")

    response = await client.get(f"/grade-levels/{grade_level.id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == str(grade_level.id)


async def test_patch_grade_level_happy_path(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    headers = await make_manage_headers(email="admin-gl8@example.com")

    response = await client.patch(
        f"/grade-levels/{grade_level.id}", json={"name": "Renamed"}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"


async def test_delete_grade_level_happy_path(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    headers = await make_manage_headers(email="admin-gl10@example.com")

    response = await client.delete(f"/grade-levels/{grade_level.id}", headers=headers)

    assert response.status_code == 204
    follow_up = await client.get(f"/grade-levels/{grade_level.id}", headers=headers)
    assert follow_up.status_code == 404


async def test_post_sections_happy_path(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    headers = await make_manage_headers(email="admin-sec1@example.com")

    response = await client.post(
        "/sections", json=make_section_payload(grade_level.id, year.id), headers=headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["grade_level_id"] == str(grade_level.id)
    assert body["academic_year_id"] == str(year.id)
    assert body["name"] == "Section A"
    assert body["capacity"] == 30
    assert body["class_teacher_id"] is None
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


async def test_post_sections_with_class_teacher_happy_path(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    teacher = await make_teacher()
    headers = await make_manage_headers(email="admin-sec2@example.com")

    response = await client.post(
        "/sections",
        json=make_section_payload(grade_level.id, year.id, class_teacher_id=str(teacher.id)),
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["class_teacher_id"] == str(teacher.id)


async def test_post_sections_duplicate_grade_year_name_returns_409(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    headers = await make_manage_headers(email="admin-sec3@example.com")
    await client.post(
        "/sections", json=make_section_payload(grade_level.id, year.id, name="Dup"), headers=headers
    )

    response = await client.post(
        "/sections", json=make_section_payload(grade_level.id, year.id, name="Dup"), headers=headers
    )

    assert response.status_code == 409


async def test_post_sections_same_name_different_academic_year_succeeds(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year_a = await make_academic_year()
    year_b = await make_academic_year()
    headers = await make_manage_headers(email="admin-sec4@example.com")
    await client.post(
        "/sections", json=make_section_payload(grade_level.id, year_a.id, name="Same"), headers=headers
    )

    response = await client.post(
        "/sections", json=make_section_payload(grade_level.id, year_b.id, name="Same"), headers=headers
    )

    assert response.status_code == 201


async def test_post_sections_nonexistent_grade_level_returns_404(
    client: AsyncClient,
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    year = await make_academic_year()
    headers = await make_manage_headers(email="admin-sec5@example.com")

    response = await client.post(
        "/sections", json=make_section_payload(uuid4(), year.id), headers=headers
    )

    assert response.status_code == 404


async def test_post_sections_nonexistent_academic_year_returns_404(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    headers = await make_manage_headers(email="admin-sec6@example.com")

    response = await client.post(
        "/sections", json=make_section_payload(grade_level.id, uuid4()), headers=headers
    )

    assert response.status_code == 404


async def test_post_sections_nonexistent_class_teacher_returns_404(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    headers = await make_manage_headers(email="admin-sec7@example.com")

    response = await client.post(
        "/sections",
        json=make_section_payload(grade_level.id, year.id, class_teacher_id=str(uuid4())),
        headers=headers,
    )

    assert response.status_code == 404


async def test_post_sections_zero_capacity_returns_422(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    headers = await make_manage_headers(email="admin-sec8@example.com")

    response = await client.post(
        "/sections", json=make_section_payload(grade_level.id, year.id, capacity=0), headers=headers
    )

    assert response.status_code == 422


async def test_post_sections_negative_capacity_returns_422(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    headers = await make_manage_headers(email="admin-sec9@example.com")

    response = await client.post(
        "/sections", json=make_section_payload(grade_level.id, year.id, capacity=-5), headers=headers
    )

    assert response.status_code == 422


async def test_post_sections_as_teacher_role_returns_403(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher-sec1@example.com")

    response = await client.post(
        "/sections", json=make_section_payload(grade_level.id, year.id), headers=headers
    )

    assert response.status_code == 403


async def test_get_sections_list_filtered_by_grade_level_id(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_section: Callable[..., Awaitable[Section]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_a = await make_grade_level(name="GA", rank=201)
    grade_b = await make_grade_level(name="GB", rank=202)
    year = await make_academic_year()
    target = await make_section(grade_a.id, year.id)
    await make_section(grade_b.id, year.id)
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher-sec2@example.com")

    response = await client.get(
        "/sections", params={"grade_level_id": str(grade_a.id)}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(target.id)


async def test_get_sections_list_filtered_by_academic_year_id(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_section: Callable[..., Awaitable[Section]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level(name="GC", rank=203)
    year_a = await make_academic_year()
    year_b = await make_academic_year()
    target = await make_section(grade_level.id, year_a.id)
    await make_section(grade_level.id, year_b.id)
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher-sec3@example.com")

    response = await client.get(
        "/sections", params={"academic_year_id": str(year_a.id)}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(target.id)


async def test_get_sections_list_pagination_smoke(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_section: Callable[..., Awaitable[Section]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level(name="GD", rank=204)
    year = await make_academic_year()
    for _ in range(3):
        await make_section(grade_level.id, year.id)
    headers = await make_manage_headers(email="admin-sec-pg@example.com")

    response = await client.get("/sections", params={"limit": 2, "offset": 0}, headers=headers)

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.headers["X-Total-Count"] == "3"


async def test_get_section_by_id_happy_path(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_section: Callable[..., Awaitable[Section]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    section = await make_section(grade_level.id, year.id)
    headers = await make_manage_headers(email="admin-sec10@example.com")

    response = await client.get(f"/sections/{section.id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == str(section.id)


async def test_get_section_by_id_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin-sec11@example.com")

    response = await client.get(f"/sections/{uuid4()}", headers=headers)

    assert response.status_code == 404


async def test_patch_section_happy_path(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_section: Callable[..., Awaitable[Section]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    section = await make_section(grade_level.id, year.id)
    headers = await make_manage_headers(email="admin-sec12@example.com")

    response = await client.patch(
        f"/sections/{section.id}", json={"capacity": 40}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["capacity"] == 40


async def test_patch_section_duplicate_name_returns_409(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_section: Callable[..., Awaitable[Section]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    await make_section(grade_level.id, year.id, name="Taken")
    other = await make_section(grade_level.id, year.id, name="Free")
    headers = await make_manage_headers(email="admin-sec13@example.com")

    response = await client.patch(
        f"/sections/{other.id}", json={"name": "Taken"}, headers=headers
    )

    assert response.status_code == 409


async def test_patch_section_nonexistent_class_teacher_returns_404(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_section: Callable[..., Awaitable[Section]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    section = await make_section(grade_level.id, year.id)
    headers = await make_manage_headers(email="admin-sec14@example.com")

    response = await client.patch(
        f"/sections/{section.id}", json={"class_teacher_id": str(uuid4())}, headers=headers
    )

    assert response.status_code == 404


async def test_patch_section_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin-sec15@example.com")

    response = await client.patch(f"/sections/{uuid4()}", json={"capacity": 10}, headers=headers)

    assert response.status_code == 404


async def test_patch_section_does_not_accept_grade_level_id_change(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_section: Callable[..., Awaitable[Section]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    # grade_level_id/academic_year_id are deliberately absent from
    # SectionUpdate — attempting to change them via PATCH is silently
    # ignored (Pydantic drops unknown fields), not applied.
    original_grade_level = await make_grade_level(name="GradeUpdateOriginal", rank=301)
    other_grade_level = await make_grade_level(name="GradeUpdateOther", rank=302)
    year = await make_academic_year()
    section = await make_section(original_grade_level.id, year.id)
    headers = await make_manage_headers(email="admin-sec16@example.com")

    response = await client.patch(
        f"/sections/{section.id}",
        json={"grade_level_id": str(other_grade_level.id), "capacity": 25},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["grade_level_id"] == str(original_grade_level.id)
    assert body["capacity"] == 25


async def test_delete_section_happy_path(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_section: Callable[..., Awaitable[Section]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    section = await make_section(grade_level.id, year.id)
    headers = await make_manage_headers(email="admin-sec17@example.com")

    response = await client.delete(f"/sections/{section.id}", headers=headers)

    assert response.status_code == 204
    follow_up = await client.get(f"/sections/{section.id}", headers=headers)
    assert follow_up.status_code == 404


async def test_delete_section_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin-sec18@example.com")

    response = await client.delete(f"/sections/{uuid4()}", headers=headers)

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST/DELETE /sections/{section_id}/students/{student_id}, GET .../students
# ---------------------------------------------------------------------------


async def test_post_section_student_happy_path(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_section: Callable[..., Awaitable[Section]],
    make_student: Callable[..., Awaitable[Student]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    section = await make_section(grade_level.id, year.id)
    student = await make_student()
    headers = await make_manage_headers(email="admin-assign1@example.com")

    response = await client.post(
        f"/sections/{section.id}/students/{student.id}", headers=headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["student_id"] == str(student.id)
    assert body["section_id"] == str(section.id)
    assert body["academic_year_id"] == str(year.id)
    assert "id" in body
    assert "assigned_at" in body


async def test_post_section_student_duplicate_same_year_returns_409(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_section: Callable[..., Awaitable[Section]],
    make_student: Callable[..., Awaitable[Student]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    section_a = await make_section(grade_level.id, year.id, name="SecA")
    section_b = await make_section(grade_level.id, year.id, name="SecB")
    student = await make_student()
    headers = await make_manage_headers(email="admin-assign2@example.com")
    await client.post(f"/sections/{section_a.id}/students/{student.id}", headers=headers)

    response = await client.post(f"/sections/{section_b.id}/students/{student.id}", headers=headers)

    assert response.status_code == 409


async def test_post_section_student_different_academic_year_succeeds(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_section: Callable[..., Awaitable[Section]],
    make_student: Callable[..., Awaitable[Student]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year_a = await make_academic_year()
    year_b = await make_academic_year()
    section_a = await make_section(grade_level.id, year_a.id)
    section_b = await make_section(grade_level.id, year_b.id)
    student = await make_student()
    headers = await make_manage_headers(email="admin-assign3@example.com")
    await client.post(f"/sections/{section_a.id}/students/{student.id}", headers=headers)

    response = await client.post(f"/sections/{section_b.id}/students/{student.id}", headers=headers)

    assert response.status_code == 201


async def test_post_section_student_section_at_capacity_returns_409(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_section: Callable[..., Awaitable[Section]],
    make_student: Callable[..., Awaitable[Student]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    section = await make_section(grade_level.id, year.id, capacity=1)
    first_student = await make_student()
    second_student = await make_student()
    headers = await make_manage_headers(email="admin-assign4@example.com")
    await client.post(f"/sections/{section.id}/students/{first_student.id}", headers=headers)

    response = await client.post(f"/sections/{section.id}/students/{second_student.id}", headers=headers)

    assert response.status_code == 409


async def test_post_section_student_nonexistent_student_returns_404(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_section: Callable[..., Awaitable[Section]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    section = await make_section(grade_level.id, year.id)
    headers = await make_manage_headers(email="admin-assign5@example.com")

    response = await client.post(f"/sections/{section.id}/students/{uuid4()}", headers=headers)

    assert response.status_code == 404


async def test_post_section_student_nonexistent_section_returns_404(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    student = await make_student()
    headers = await make_manage_headers(email="admin-assign6@example.com")

    response = await client.post(f"/sections/{uuid4()}/students/{student.id}", headers=headers)

    assert response.status_code == 404


async def test_post_section_student_as_teacher_role_returns_403(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_section: Callable[..., Awaitable[Section]],
    make_student: Callable[..., Awaitable[Student]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    section = await make_section(grade_level.id, year.id)
    student = await make_student()
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher-assign1@example.com")

    response = await client.post(f"/sections/{section.id}/students/{student.id}", headers=headers)

    assert response.status_code == 403


async def test_get_section_students_roster(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_section: Callable[..., Awaitable[Section]],
    make_student: Callable[..., Awaitable[Student]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    section = await make_section(grade_level.id, year.id)
    student_a = await make_student()
    student_b = await make_student()
    headers = await make_manage_headers(email="admin-roster1@example.com")
    await client.post(f"/sections/{section.id}/students/{student_a.id}", headers=headers)
    await client.post(f"/sections/{section.id}/students/{student_b.id}", headers=headers)

    response = await client.get(f"/sections/{section.id}/students", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert {r["student_id"] for r in body} == {str(student_a.id), str(student_b.id)}


async def test_get_section_students_roster_empty(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_section: Callable[..., Awaitable[Section]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    section = await make_section(grade_level.id, year.id)
    headers = await make_manage_headers(email="admin-roster2@example.com")

    response = await client.get(f"/sections/{section.id}/students", headers=headers)

    assert response.status_code == 200
    assert response.json() == []


async def test_delete_section_student_happy_path(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_section: Callable[..., Awaitable[Section]],
    make_student: Callable[..., Awaitable[Student]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    section = await make_section(grade_level.id, year.id)
    student = await make_student()
    headers = await make_manage_headers(email="admin-unassign1@example.com")
    await client.post(f"/sections/{section.id}/students/{student.id}", headers=headers)

    response = await client.delete(f"/sections/{section.id}/students/{student.id}", headers=headers)

    assert response.status_code == 204
    roster = await client.get(f"/sections/{section.id}/students", headers=headers)
    assert roster.json() == []


async def test_delete_section_student_not_assigned_returns_404(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_section: Callable[..., Awaitable[Section]],
    make_student: Callable[..., Awaitable[Student]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    section = await make_section(grade_level.id, year.id)
    student = await make_student()
    headers = await make_manage_headers(email="admin-unassign2@example.com")

    response = await client.delete(f"/sections/{section.id}/students/{student.id}", headers=headers)

    assert response.status_code == 404


async def test_post_section_class_attaches_and_returns_section(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_section: Callable[..., Awaitable[Section]],
    make_classable: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    section = await make_section(grade_level.id, year.id)
    klass = await make_classable(academic_year_id=year.id)
    headers = await make_manage_headers(email="admin-attach1@example.com")

    response = await client.post(f"/sections/{section.id}/classes/{klass.id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == str(section.id)


async def test_post_section_class_backfills_enrollments_for_existing_members(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_section: Callable[..., Awaitable[Section]],
    make_student: Callable[..., Awaitable[Student]],
    make_classable: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    section = await make_section(grade_level.id, year.id)
    student_a = await make_student()
    student_b = await make_student()
    headers = await make_manage_headers(email="admin-attach2@example.com")
    await client.post(f"/sections/{section.id}/students/{student_a.id}", headers=headers)
    await client.post(f"/sections/{section.id}/students/{student_b.id}", headers=headers)
    klass = await make_classable(academic_year_id=year.id)

    await client.post(f"/sections/{section.id}/classes/{klass.id}", headers=headers)

    enrollments = await client.get("/enrollments", params={"class_id": str(klass.id)}, headers=headers)
    assert enrollments.status_code == 200
    assert {e["student_id"] for e in enrollments.json()} == {str(student_a.id), str(student_b.id)}


async def test_post_section_class_attach_is_idempotent(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_section: Callable[..., Awaitable[Section]],
    make_student: Callable[..., Awaitable[Student]],
    make_classable: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    section = await make_section(grade_level.id, year.id)
    student = await make_student()
    headers = await make_manage_headers(email="admin-attach3@example.com")
    await client.post(f"/sections/{section.id}/students/{student.id}", headers=headers)
    klass = await make_classable(academic_year_id=year.id)

    await client.post(f"/sections/{section.id}/classes/{klass.id}", headers=headers)
    second = await client.post(f"/sections/{section.id}/classes/{klass.id}", headers=headers)

    assert second.status_code == 200
    enrollments = await client.get("/enrollments", params={"class_id": str(klass.id)}, headers=headers)
    assert len(enrollments.json()) == 1


async def test_post_section_class_nonexistent_class_returns_404(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_section: Callable[..., Awaitable[Section]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    section = await make_section(grade_level.id, year.id)
    headers = await make_manage_headers(email="admin-attach5@example.com")

    response = await client.post(f"/sections/{section.id}/classes/{uuid4()}", headers=headers)

    assert response.status_code == 404


async def test_delete_section_class_detaches_and_leaves_enrollments_intact(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_section: Callable[..., Awaitable[Section]],
    make_student: Callable[..., Awaitable[Student]],
    make_classable: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    section = await make_section(grade_level.id, year.id)
    student = await make_student()
    headers = await make_manage_headers(email="admin-detach1@example.com")
    await client.post(f"/sections/{section.id}/students/{student.id}", headers=headers)
    klass = await make_classable(academic_year_id=year.id)
    await client.post(f"/sections/{section.id}/classes/{klass.id}", headers=headers)

    response = await client.delete(f"/sections/{section.id}/classes/{klass.id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == str(section.id)
    enrollments = await client.get("/enrollments", params={"class_id": str(klass.id)}, headers=headers)
    assert len(enrollments.json()) == 1




async def test_post_section_class_from_different_year_returns_409(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_section: Callable[..., Awaitable[Section]],
    make_classable: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    grade_level = await make_grade_level()
    year = await make_academic_year()
    section = await make_section(grade_level.id, year.id)
    other_year = await make_academic_year()
    foreign_class = await make_classable(academic_year_id=other_year.id)
    headers = await make_manage_headers(email="admin-yearmismatch@example.com")

    response = await client.post(
        f"/sections/{section.id}/classes/{foreign_class.id}", headers=headers
    )

    assert response.status_code == 409


async def test_get_section_students_as_student_role_returns_403(
    client: AsyncClient,
    make_grade_level: Callable[..., Awaitable[GradeLevel]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_section: Callable[..., Awaitable[Section]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    # The roster is ADMIN+TEACHER only: left open it reconstructs, by join
    # with GET /classes, the classmate->classes mapping docs/adr/0023
    # deliberately withholds from a STUDENT.
    grade_level = await make_grade_level()
    year = await make_academic_year()
    section = await make_section(grade_level.id, year.id)
    student_headers = await make_manage_headers(
        role=UserRole.STUDENT, email="student-roster@example.com"
    )

    response = await client.get(f"/sections/{section.id}/students", headers=student_headers)

    assert response.status_code == 403
