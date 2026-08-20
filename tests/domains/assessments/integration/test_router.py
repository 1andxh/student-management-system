from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from sms.domains.academic_years.models import AcademicYear, Term
from sms.domains.assessments.models import Assessment
from sms.domains.classes.models import Class, Subject
from sms.domains.enrollments.models import Enrollment, EnrollmentStatus
from sms.domains.students.models import Student
from sms.domains.teachers.models import Teacher
from sms.domains.users.models import User, UserRole


def make_assessment_payload(class_id: object, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "class_id": str(class_id),
        "name": "Midterm Exam",
        "type": "exam",
        "max_score": "100.00",
        "date": "2024-10-15",
    }
    payload.update(overrides)
    return payload


def make_grade_payload(assessment_id: object, student_id: object, **overrides: object) -> dict:
    payload: dict[str, object] = {
        "assessment_id": str(assessment_id),
        "student_id": str(student_id),
        "score": "85.00",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# local factory fixtures — Subject/AcademicYear/Term/Teacher/Class mirrors
# tests/domains/classes/integration/test_router.py and
# tests/domains/enrollments/integration/test_router.py exactly (neither
# file's fixtures are shared to conftest.py, same convention followed here).
# Student additionally supports linking to a User via user_id, needed for
# the STUDENT self-view tests (docs/adr/0018-equivalent scoping in
# GradeService).
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
def make_class_instance(
    make_subject: Callable[..., Awaitable[Subject]],
    make_term: Callable[..., Awaitable[Term]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_class: Callable[..., Awaitable[Class]],
):
    """Convenience wrapper — most assessment/grade tests just need *a*
    class and don't care about its Subject/Term/Teacher, matching
    make_enrollable_class in tests/domains/enrollments/integration."""

    async def _make(**overrides: object) -> Class:
        subject = await make_subject()
        term = await make_term()
        teacher = await make_teacher()
        return await make_class(subject.id, term.id, teacher.id, **overrides)

    return _make


@pytest.fixture
def make_enrollment(db_session: AsyncSession):
    async def _make_enrollment(
        student_id: object, class_id: object, **overrides: object
    ) -> Enrollment:
        defaults: dict[str, object] = {
            "student_id": student_id,
            "class_id": class_id,
            "status": EnrollmentStatus.ACTIVE,
        }
        defaults.update(overrides)
        enrollment = Enrollment(**defaults)
        db_session.add(enrollment)
        await db_session.commit()
        await db_session.refresh(enrollment)
        return enrollment

    return _make_enrollment


@pytest.fixture
def make_manage_headers(
    make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
):
    """Auth header for a user with the given role — admin by default (both
    ADMIN and TEACHER can manage assessments/grades). Pass
    role=UserRole.STUDENT to exercise the "authenticated but not allowed to
    mutate" path instead."""

    async def _make_headers(role: UserRole = UserRole.ADMIN, **overrides: object) -> dict[str, str]:
        user = await make_user(role=role, **overrides)
        return auth_headers(user)

    return _make_headers


@pytest.fixture
def make_student_with_headers(
    make_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[User], dict[str, str]],
    make_student: Callable[..., Awaitable[Student]],
):
    """Creates a User (role=STUDENT) AND a Student record linked to that
    same user via user_id, together — needed for the self-view tests, since
    GradeService resolves "my own student record" via
    StudentRepository.get_by_user_id(current_user.id)."""

    async def _make(**overrides: object) -> tuple[Student, dict[str, str]]:
        unique = uuid4().hex[:8]
        user_overrides: dict[str, object] = {"email": f"student{unique}@example.com"}
        user_overrides.update(overrides)
        user = await make_user(role=UserRole.STUDENT, **user_overrides)
        student = await make_student(user_id=user.id)
        return student, auth_headers(user)

    return _make


@pytest.fixture
def make_class_for_teacher(
    make_subject: Callable[..., Awaitable[Subject]],
    make_term: Callable[..., Awaitable[Term]],
    make_class: Callable[..., Awaitable[Class]],
):
    """Like make_class_instance, but for a specific teacher_id — used to
    build a Class actually owned (or not owned) by a given Teacher for the
    TEACHER class-ownership scoping tests."""

    async def _make(teacher_id: object, **overrides: object) -> Class:
        subject = await make_subject()
        term = await make_term()
        return await make_class(subject.id, term.id, teacher_id, **overrides)

    return _make


@pytest.fixture
def make_teacher_with_headers(
    make_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[User], dict[str, str]],
    make_teacher: Callable[..., Awaitable[Teacher]],
):
    """Creates a User (role=TEACHER) AND a Teacher record linked to that
    same user via user_id, together — needed for the TEACHER
    class-ownership scoping tests, since AssessmentService/GradeService
    resolve "my own teacher record" via
    TeacherRepository.get_by_user_id(current_user.id). Mirrors
    make_student_with_headers above."""

    async def _make(**overrides: object) -> tuple[Teacher, dict[str, str]]:
        unique = uuid4().hex[:8]
        user_overrides: dict[str, object] = {"email": f"teacheruser{unique}@example.com"}
        user_overrides.update(overrides)
        user = await make_user(role=UserRole.TEACHER, **user_overrides)
        teacher = await make_teacher(user_id=user.id, email=f"teacherrec{unique}@example.com")
        return teacher, auth_headers(user)

    return _make


@pytest.fixture
async def enrolled_setup(
    make_student: Callable[..., Awaitable[Student]],
    make_class_instance: Callable[..., Awaitable[Class]],
    make_enrollment: Callable[..., Awaitable[Enrollment]],
) -> tuple[Student, Class]:
    """A Student actively enrolled in a Class — the minimum needed before a
    Grade can be entered for that student against an Assessment in that
    class."""
    student = await make_student()
    klass = await make_class_instance()
    await make_enrollment(student.id, klass.id, status=EnrollmentStatus.ACTIVE)
    return student, klass


# ---------------------------------------------------------------------------
# POST /assessments
# ---------------------------------------------------------------------------


async def test_post_assessments_happy_path(
    client: AsyncClient,
    make_class_instance: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    klass = await make_class_instance()
    headers = await make_manage_headers(email="admin1@example.com")

    response = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["class_id"] == str(klass.id)
    assert body["name"] == "Midterm Exam"
    assert body["type"] == "exam"
    assert body["max_score"] == "100.00"
    assert body["date"] == "2024-10-15"
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


async def test_post_assessments_nonexistent_class_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin2@example.com")

    response = await client.post(
        "/assessments", json=make_assessment_payload(uuid4()), headers=headers
    )

    assert response.status_code == 404


async def test_post_assessments_without_token_returns_401(
    client: AsyncClient, make_class_instance: Callable[..., Awaitable[Class]]
) -> None:
    klass = await make_class_instance()

    response = await client.post("/assessments", json=make_assessment_payload(klass.id))

    assert response.status_code == 401


async def test_post_assessments_as_student_role_returns_403(
    client: AsyncClient,
    make_class_instance: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    klass = await make_class_instance()
    headers = await make_manage_headers(role=UserRole.STUDENT, email="student1@example.com")

    response = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=headers
    )

    assert response.status_code == 403


async def test_post_assessments_as_teacher_who_owns_class_succeeds(
    client: AsyncClient,
    make_class_for_teacher: Callable[..., Awaitable[Class]],
    make_teacher_with_headers: Callable[..., Awaitable[tuple[Teacher, dict[str, str]]]],
) -> None:
    teacher, teacher_headers = await make_teacher_with_headers()
    owned_class = await make_class_for_teacher(teacher.id)

    response = await client.post(
        "/assessments", json=make_assessment_payload(owned_class.id), headers=teacher_headers
    )

    assert response.status_code == 201
    assert response.json()["class_id"] == str(owned_class.id)


async def test_post_assessments_as_teacher_not_owning_class_returns_403(
    client: AsyncClient,
    make_class_instance: Callable[..., Awaitable[Class]],
    make_teacher_with_headers: Callable[..., Awaitable[tuple[Teacher, dict[str, str]]]],
) -> None:
    klass = await make_class_instance()  # owned by an unrelated teacher
    _teacher, teacher_headers = await make_teacher_with_headers()

    response = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=teacher_headers
    )

    assert response.status_code == 403


async def test_post_assessments_as_teacher_with_no_linked_teacher_record_returns_403(
    client: AsyncClient,
    make_class_instance: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    klass = await make_class_instance()
    orphan_teacher_headers = await make_manage_headers(
        role=UserRole.TEACHER, email="orphan-teacher1@example.com"
    )

    response = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=orphan_teacher_headers
    )

    assert response.status_code == 403


async def test_post_assessments_as_admin_succeeds_regardless_of_class_ownership(
    client: AsyncClient,
    make_class_for_teacher: Callable[..., Awaitable[Class]],
    make_teacher_with_headers: Callable[..., Awaitable[tuple[Teacher, dict[str, str]]]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    teacher, _teacher_headers = await make_teacher_with_headers()
    someone_elses_class = await make_class_for_teacher(teacher.id)
    admin_headers = await make_manage_headers(email="admin-owner-check@example.com")

    response = await client.post(
        "/assessments", json=make_assessment_payload(someone_elses_class.id), headers=admin_headers
    )

    assert response.status_code == 201


# ---------------------------------------------------------------------------
# GET /assessments
# ---------------------------------------------------------------------------


async def test_get_assessments_list(
    client: AsyncClient,
    make_class_instance: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    klass = await make_class_instance()
    headers = await make_manage_headers(email="admin3@example.com")
    await client.post("/assessments", json=make_assessment_payload(klass.id), headers=headers)
    await client.post(
        "/assessments",
        json=make_assessment_payload(klass.id, name="Final Exam"),
        headers=headers,
    )

    response = await client.get("/assessments", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 2


async def test_get_assessment_by_id_happy_path(
    client: AsyncClient,
    make_class_instance: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    klass = await make_class_instance()
    headers = await make_manage_headers(email="admin4@example.com")
    created = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=headers
    )
    assessment_id = created.json()["id"]

    response = await client.get(f"/assessments/{assessment_id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == assessment_id


async def test_get_assessment_by_id_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin5@example.com")

    response = await client.get(f"/assessments/{uuid4()}", headers=headers)

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_get_assessments_list_as_teacher_returns_only_own_classes(
    client: AsyncClient,
    make_class_instance: Callable[..., Awaitable[Class]],
    make_class_for_teacher: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
    make_teacher_with_headers: Callable[..., Awaitable[tuple[Teacher, dict[str, str]]]],
) -> None:
    teacher, teacher_headers = await make_teacher_with_headers()
    owned_class = await make_class_for_teacher(teacher.id)
    other_class = await make_class_instance()
    admin_headers = await make_manage_headers(email="admin-list-scope@example.com")
    owned_assessment = await client.post(
        "/assessments", json=make_assessment_payload(owned_class.id), headers=admin_headers
    )
    await client.post(
        "/assessments", json=make_assessment_payload(other_class.id), headers=admin_headers
    )

    response = await client.get("/assessments", headers=teacher_headers)

    assert response.status_code == 200
    body = response.json()
    assert [a["id"] for a in body] == [owned_assessment.json()["id"]]


async def test_get_assessment_by_id_as_teacher_who_owns_class_succeeds(
    client: AsyncClient,
    make_class_for_teacher: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
    make_teacher_with_headers: Callable[..., Awaitable[tuple[Teacher, dict[str, str]]]],
) -> None:
    teacher, teacher_headers = await make_teacher_with_headers()
    owned_class = await make_class_for_teacher(teacher.id)
    admin_headers = await make_manage_headers(email="admin-get-own@example.com")
    created = await client.post(
        "/assessments", json=make_assessment_payload(owned_class.id), headers=admin_headers
    )
    assessment_id = created.json()["id"]

    response = await client.get(f"/assessments/{assessment_id}", headers=teacher_headers)

    assert response.status_code == 200
    assert response.json()["id"] == assessment_id


async def test_get_assessment_by_id_as_teacher_not_owning_class_returns_403(
    client: AsyncClient,
    make_class_instance: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
    make_teacher_with_headers: Callable[..., Awaitable[tuple[Teacher, dict[str, str]]]],
) -> None:
    klass = await make_class_instance()
    admin_headers = await make_manage_headers(email="admin-get-notown@example.com")
    created = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=admin_headers
    )
    assessment_id = created.json()["id"]
    _teacher, teacher_headers = await make_teacher_with_headers()

    response = await client.get(f"/assessments/{assessment_id}", headers=teacher_headers)

    assert response.status_code == 403


async def test_get_assessments_list_pagination_slices_and_sets_total_count_header(
    client: AsyncClient,
    make_class_instance: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    klass = await make_class_instance()
    headers = await make_manage_headers(email="admin-pg-assess@example.com")
    for i in range(5):
        await client.post(
            "/assessments",
            json=make_assessment_payload(klass.id, name=f"Assess-PG-{i}"),
            headers=headers,
        )

    response = await client.get("/assessments", params={"limit": 2, "offset": 0}, headers=headers)

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.headers["X-Total-Count"] == "5"


async def test_get_assessments_list_newest_first_ordering(
    client: AsyncClient,
    db_session: AsyncSession,
    make_class_instance: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    klass = await make_class_instance()
    headers = await make_manage_headers(email="admin-ord-assess@example.com")
    first = await client.post(
        "/assessments", json=make_assessment_payload(klass.id, name="Ord-1"), headers=headers
    )
    second = await client.post(
        "/assessments", json=make_assessment_payload(klass.id, name="Ord-2"), headers=headers
    )
    # Assessment has no created_at field on its create schema (it's a
    # server-generated column, not client-settable via POST), so the only
    # way to give the two rows distinguishable timestamps is a direct
    # post-creation UPDATE. Needed because db_session wraps this whole test
    # in one outer Postgres transaction (SAVEPOINT-based rollback, see
    # conftest.py) — func.now()/CURRENT_TIMESTAMP is transaction-scoped,
    # not statement-scoped, so both POSTs would otherwise get an identical
    # server-default created_at.
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    await db_session.execute(
        update(Assessment)
        .where(Assessment.id == UUID(first.json()["id"]))
        .values(created_at=base)
    )
    await db_session.execute(
        update(Assessment)
        .where(Assessment.id == UUID(second.json()["id"]))
        .values(created_at=base + timedelta(minutes=1))
    )
    await db_session.commit()

    response = await client.get("/assessments", headers=headers)

    assert response.status_code == 200
    ids = [a["id"] for a in response.json()]
    assert ids.index(second.json()["id"]) < ids.index(first.json()["id"])


async def test_get_assessments_list_filtered_by_class_id(
    client: AsyncClient,
    make_class_instance: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    class_a = await make_class_instance()
    class_b = await make_class_instance()
    headers = await make_manage_headers(email="admin-filter-assess@example.com")
    target = await client.post(
        "/assessments", json=make_assessment_payload(class_a.id), headers=headers
    )
    await client.post("/assessments", json=make_assessment_payload(class_b.id), headers=headers)

    response = await client.get(
        "/assessments", params={"class_id": str(class_a.id)}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == target.json()["id"]


async def test_get_assessments_list_as_teacher_explicit_owned_class_id_succeeds(
    client: AsyncClient,
    make_class_for_teacher: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
    make_teacher_with_headers: Callable[..., Awaitable[tuple[Teacher, dict[str, str]]]],
) -> None:
    teacher, teacher_headers = await make_teacher_with_headers()
    owned_class = await make_class_for_teacher(teacher.id)
    admin_headers = await make_manage_headers(email="admin-filter-owned@example.com")
    created = await client.post(
        "/assessments", json=make_assessment_payload(owned_class.id), headers=admin_headers
    )

    response = await client.get(
        "/assessments", params={"class_id": str(owned_class.id)}, headers=teacher_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == created.json()["id"]


async def test_get_assessments_list_as_teacher_explicit_not_owned_class_id_returns_403(
    client: AsyncClient,
    make_class_instance: Callable[..., Awaitable[Class]],
    make_teacher_with_headers: Callable[..., Awaitable[tuple[Teacher, dict[str, str]]]],
) -> None:
    klass = await make_class_instance()  # owned by an unrelated teacher
    _teacher, teacher_headers = await make_teacher_with_headers()

    response = await client.get(
        "/assessments", params={"class_id": str(klass.id)}, headers=teacher_headers
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /assessments/{id}
# ---------------------------------------------------------------------------


async def test_patch_assessment_happy_path(
    client: AsyncClient,
    make_class_instance: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    klass = await make_class_instance()
    headers = await make_manage_headers(email="admin6@example.com")
    created = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=headers
    )
    assessment_id = created.json()["id"]

    response = await client.patch(
        f"/assessments/{assessment_id}", json={"name": "Final Exam"}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == assessment_id
    assert body["name"] == "Final Exam"


async def test_patch_assessment_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin7@example.com")

    response = await client.patch(
        f"/assessments/{uuid4()}", json={"name": "Nobody"}, headers=headers
    )

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_patch_assessment_as_student_role_returns_403(
    client: AsyncClient,
    make_class_instance: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    klass = await make_class_instance()
    admin_headers = await make_manage_headers(email="admin8@example.com")
    created = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=admin_headers
    )
    assessment_id = created.json()["id"]
    student_headers = await make_manage_headers(
        role=UserRole.STUDENT, email="student2@example.com"
    )

    response = await client.patch(
        f"/assessments/{assessment_id}", json={"name": "Nope"}, headers=student_headers
    )

    assert response.status_code == 403


async def test_patch_assessment_as_teacher_who_owns_class_succeeds(
    client: AsyncClient,
    make_class_for_teacher: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
    make_teacher_with_headers: Callable[..., Awaitable[tuple[Teacher, dict[str, str]]]],
) -> None:
    teacher, teacher_headers = await make_teacher_with_headers()
    owned_class = await make_class_for_teacher(teacher.id)
    admin_headers = await make_manage_headers(email="admin-patch-own@example.com")
    created = await client.post(
        "/assessments", json=make_assessment_payload(owned_class.id), headers=admin_headers
    )
    assessment_id = created.json()["id"]

    response = await client.patch(
        f"/assessments/{assessment_id}", json={"name": "Retake"}, headers=teacher_headers
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Retake"


async def test_patch_assessment_as_teacher_not_owning_class_returns_403(
    client: AsyncClient,
    make_class_instance: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
    make_teacher_with_headers: Callable[..., Awaitable[tuple[Teacher, dict[str, str]]]],
) -> None:
    klass = await make_class_instance()
    admin_headers = await make_manage_headers(email="admin-patch-notown@example.com")
    created = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=admin_headers
    )
    assessment_id = created.json()["id"]
    _teacher, teacher_headers = await make_teacher_with_headers()

    response = await client.patch(
        f"/assessments/{assessment_id}", json={"name": "Nope"}, headers=teacher_headers
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /assessments/{id}
# ---------------------------------------------------------------------------


async def test_delete_assessment_happy_path(
    client: AsyncClient,
    make_class_instance: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    klass = await make_class_instance()
    headers = await make_manage_headers(email="admin9@example.com")
    created = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=headers
    )
    assessment_id = created.json()["id"]

    response = await client.delete(f"/assessments/{assessment_id}", headers=headers)

    assert response.status_code == 204

    follow_up = await client.get(f"/assessments/{assessment_id}", headers=headers)
    assert follow_up.status_code == 404


async def test_delete_assessment_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin10@example.com")

    response = await client.delete(f"/assessments/{uuid4()}", headers=headers)

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_delete_assessment_as_teacher_who_owns_class_succeeds(
    client: AsyncClient,
    make_class_for_teacher: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
    make_teacher_with_headers: Callable[..., Awaitable[tuple[Teacher, dict[str, str]]]],
) -> None:
    teacher, teacher_headers = await make_teacher_with_headers()
    owned_class = await make_class_for_teacher(teacher.id)
    admin_headers = await make_manage_headers(email="admin-delete-own@example.com")
    created = await client.post(
        "/assessments", json=make_assessment_payload(owned_class.id), headers=admin_headers
    )
    assessment_id = created.json()["id"]

    response = await client.delete(f"/assessments/{assessment_id}", headers=teacher_headers)

    assert response.status_code == 204


async def test_delete_assessment_as_teacher_not_owning_class_returns_403(
    client: AsyncClient,
    make_class_instance: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
    make_teacher_with_headers: Callable[..., Awaitable[tuple[Teacher, dict[str, str]]]],
) -> None:
    klass = await make_class_instance()
    admin_headers = await make_manage_headers(email="admin-delete-notown@example.com")
    created = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=admin_headers
    )
    assessment_id = created.json()["id"]
    _teacher, teacher_headers = await make_teacher_with_headers()

    response = await client.delete(f"/assessments/{assessment_id}", headers=teacher_headers)

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# POST /grades
# ---------------------------------------------------------------------------


async def test_post_grades_happy_path(
    client: AsyncClient,
    enrolled_setup: tuple[Student, Class],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    student, klass = enrolled_setup
    headers = await make_manage_headers(email="admin11@example.com")
    assessment = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=headers
    )
    assessment_id = assessment.json()["id"]

    response = await client.post(
        "/grades", json=make_grade_payload(assessment_id, student.id), headers=headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["assessment_id"] == assessment_id
    assert body["student_id"] == str(student.id)
    assert body["score"] == "85.00"
    assert "id" in body
    assert "graded_at" in body


async def test_post_grades_score_exceeds_max_score_returns_409(
    client: AsyncClient,
    enrolled_setup: tuple[Student, Class],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    student, klass = enrolled_setup
    headers = await make_manage_headers(email="admin12@example.com")
    assessment = await client.post(
        "/assessments",
        json=make_assessment_payload(klass.id, max_score="50.00"),
        headers=headers,
    )
    assessment_id = assessment.json()["id"]

    response = await client.post(
        "/grades",
        json=make_grade_payload(assessment_id, student.id, score="75.00"),
        headers=headers,
    )

    assert response.status_code == 409


async def test_post_grades_student_not_enrolled_returns_409(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_class_instance: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    # deliberately no Enrollment created for this student/class pair
    student = await make_student()
    klass = await make_class_instance()
    headers = await make_manage_headers(email="admin13@example.com")
    assessment = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=headers
    )
    assessment_id = assessment.json()["id"]

    response = await client.post(
        "/grades", json=make_grade_payload(assessment_id, student.id), headers=headers
    )

    assert response.status_code == 409


async def test_post_grades_duplicate_returns_409(
    client: AsyncClient,
    enrolled_setup: tuple[Student, Class],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    student, klass = enrolled_setup
    headers = await make_manage_headers(email="admin14@example.com")
    assessment = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=headers
    )
    assessment_id = assessment.json()["id"]
    await client.post(
        "/grades", json=make_grade_payload(assessment_id, student.id), headers=headers
    )

    response = await client.post(
        "/grades", json=make_grade_payload(assessment_id, student.id), headers=headers
    )

    assert response.status_code == 409


async def test_post_grades_nonexistent_assessment_returns_404(
    client: AsyncClient,
    enrolled_setup: tuple[Student, Class],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    student, _klass = enrolled_setup
    headers = await make_manage_headers(email="admin15@example.com")

    response = await client.post(
        "/grades", json=make_grade_payload(uuid4(), student.id), headers=headers
    )

    assert response.status_code == 404


async def test_post_grades_nonexistent_student_returns_404(
    client: AsyncClient,
    make_class_instance: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    klass = await make_class_instance()
    headers = await make_manage_headers(email="admin16@example.com")
    assessment = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=headers
    )
    assessment_id = assessment.json()["id"]

    response = await client.post(
        "/grades", json=make_grade_payload(assessment_id, uuid4()), headers=headers
    )

    assert response.status_code == 404


async def test_post_grades_without_token_returns_401(
    client: AsyncClient, enrolled_setup: tuple[Student, Class]
) -> None:
    student, _klass = enrolled_setup

    response = await client.post("/grades", json=make_grade_payload(uuid4(), student.id))

    assert response.status_code == 401


async def test_post_grades_as_student_role_returns_403(
    client: AsyncClient,
    enrolled_setup: tuple[Student, Class],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    student, klass = enrolled_setup
    admin_headers = await make_manage_headers(email="admin17@example.com")
    assessment = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=admin_headers
    )
    assessment_id = assessment.json()["id"]
    student_headers = await make_manage_headers(
        role=UserRole.STUDENT, email="student3@example.com"
    )

    response = await client.post(
        "/grades",
        json=make_grade_payload(assessment_id, student.id),
        headers=student_headers,
    )

    assert response.status_code == 403


async def test_post_grades_as_teacher_who_owns_class_succeeds(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_class_for_teacher: Callable[..., Awaitable[Class]],
    make_enrollment: Callable[..., Awaitable[Enrollment]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
    make_teacher_with_headers: Callable[..., Awaitable[tuple[Teacher, dict[str, str]]]],
) -> None:
    teacher, teacher_headers = await make_teacher_with_headers()
    owned_class = await make_class_for_teacher(teacher.id)
    student = await make_student()
    await make_enrollment(student.id, owned_class.id, status=EnrollmentStatus.ACTIVE)
    admin_headers = await make_manage_headers(email="admin-grade-post-own@example.com")
    assessment = await client.post(
        "/assessments", json=make_assessment_payload(owned_class.id), headers=admin_headers
    )
    assessment_id = assessment.json()["id"]

    response = await client.post(
        "/grades", json=make_grade_payload(assessment_id, student.id), headers=teacher_headers
    )

    assert response.status_code == 201
    assert response.json()["student_id"] == str(student.id)


async def test_post_grades_as_teacher_not_owning_class_returns_403(
    client: AsyncClient,
    enrolled_setup: tuple[Student, Class],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
    make_teacher_with_headers: Callable[..., Awaitable[tuple[Teacher, dict[str, str]]]],
) -> None:
    student, klass = enrolled_setup  # klass is owned by an unrelated teacher
    admin_headers = await make_manage_headers(email="admin-grade-post-notown@example.com")
    assessment = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=admin_headers
    )
    assessment_id = assessment.json()["id"]
    _teacher, teacher_headers = await make_teacher_with_headers()

    response = await client.post(
        "/grades", json=make_grade_payload(assessment_id, student.id), headers=teacher_headers
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET /grades
# ---------------------------------------------------------------------------


async def test_get_grades_list_as_admin_sees_all(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_class_instance: Callable[..., Awaitable[Class]],
    make_enrollment: Callable[..., Awaitable[Enrollment]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    klass = await make_class_instance()
    student_a = await make_student()
    student_b = await make_student()
    await make_enrollment(student_a.id, klass.id, status=EnrollmentStatus.ACTIVE)
    await make_enrollment(student_b.id, klass.id, status=EnrollmentStatus.ACTIVE)
    headers = await make_manage_headers(email="admin18@example.com")
    assessment = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=headers
    )
    assessment_id = assessment.json()["id"]
    await client.post(
        "/grades", json=make_grade_payload(assessment_id, student_a.id), headers=headers
    )
    await client.post(
        "/grades", json=make_grade_payload(assessment_id, student_b.id), headers=headers
    )

    response = await client.get("/grades", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert {g["student_id"] for g in body} == {str(student_a.id), str(student_b.id)}


async def test_get_grades_list_as_student_sees_only_own(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_student_with_headers: Callable[..., Awaitable[tuple[Student, dict[str, str]]]],
    make_class_instance: Callable[..., Awaitable[Class]],
    make_enrollment: Callable[..., Awaitable[Enrollment]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    klass = await make_class_instance()
    own_student, own_student_headers = await make_student_with_headers()
    other_student = await make_student()
    await make_enrollment(own_student.id, klass.id, status=EnrollmentStatus.ACTIVE)
    await make_enrollment(other_student.id, klass.id, status=EnrollmentStatus.ACTIVE)
    admin_headers = await make_manage_headers(email="admin19@example.com")
    assessment = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=admin_headers
    )
    assessment_id = assessment.json()["id"]
    await client.post(
        "/grades",
        json=make_grade_payload(assessment_id, own_student.id),
        headers=admin_headers,
    )
    await client.post(
        "/grades",
        json=make_grade_payload(assessment_id, other_student.id),
        headers=admin_headers,
    )

    response = await client.get("/grades", headers=own_student_headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["student_id"] == str(own_student.id)


async def test_get_grades_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/grades")

    assert response.status_code == 401


async def test_get_grades_list_as_teacher_sees_only_own_classes(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_class_instance: Callable[..., Awaitable[Class]],
    make_class_for_teacher: Callable[..., Awaitable[Class]],
    make_enrollment: Callable[..., Awaitable[Enrollment]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
    make_teacher_with_headers: Callable[..., Awaitable[tuple[Teacher, dict[str, str]]]],
) -> None:
    teacher, teacher_headers = await make_teacher_with_headers()
    owned_class = await make_class_for_teacher(teacher.id)
    other_class = await make_class_instance()
    owned_student = await make_student()
    other_student = await make_student()
    await make_enrollment(owned_student.id, owned_class.id, status=EnrollmentStatus.ACTIVE)
    await make_enrollment(other_student.id, other_class.id, status=EnrollmentStatus.ACTIVE)
    admin_headers = await make_manage_headers(email="admin-grade-list-scope@example.com")
    owned_assessment = await client.post(
        "/assessments", json=make_assessment_payload(owned_class.id), headers=admin_headers
    )
    other_assessment = await client.post(
        "/assessments", json=make_assessment_payload(other_class.id), headers=admin_headers
    )
    owned_grade = await client.post(
        "/grades",
        json=make_grade_payload(owned_assessment.json()["id"], owned_student.id),
        headers=admin_headers,
    )
    await client.post(
        "/grades",
        json=make_grade_payload(other_assessment.json()["id"], other_student.id),
        headers=admin_headers,
    )

    response = await client.get("/grades", headers=teacher_headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == owned_grade.json()["id"]


async def test_get_grades_list_as_teacher_explicit_class_id_not_owned_returns_403(
    client: AsyncClient,
    make_class_instance: Callable[..., Awaitable[Class]],
    make_teacher_with_headers: Callable[..., Awaitable[tuple[Teacher, dict[str, str]]]],
) -> None:
    klass = await make_class_instance()  # owned by an unrelated teacher
    _teacher, teacher_headers = await make_teacher_with_headers()

    response = await client.get("/grades", params={"class_id": str(klass.id)}, headers=teacher_headers)

    assert response.status_code == 403


async def test_get_grades_list_pagination_slices_and_sets_total_count_header(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_class_instance: Callable[..., Awaitable[Class]],
    make_enrollment: Callable[..., Awaitable[Enrollment]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    klass = await make_class_instance()
    headers = await make_manage_headers(email="admin-pg-grades@example.com")
    assessment = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=headers
    )
    assessment_id = assessment.json()["id"]
    for _ in range(5):
        student = await make_student()
        await make_enrollment(student.id, klass.id, status=EnrollmentStatus.ACTIVE)
        await client.post(
            "/grades", json=make_grade_payload(assessment_id, student.id), headers=headers
        )

    response = await client.get("/grades", params={"limit": 2, "offset": 0}, headers=headers)

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.headers["X-Total-Count"] == "5"


# ---------------------------------------------------------------------------
# GET /grades/{id}
# ---------------------------------------------------------------------------


async def test_get_grade_by_id_as_owning_student_happy_path(
    client: AsyncClient,
    make_student_with_headers: Callable[..., Awaitable[tuple[Student, dict[str, str]]]],
    make_class_instance: Callable[..., Awaitable[Class]],
    make_enrollment: Callable[..., Awaitable[Enrollment]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    klass = await make_class_instance()
    own_student, own_student_headers = await make_student_with_headers()
    await make_enrollment(own_student.id, klass.id, status=EnrollmentStatus.ACTIVE)
    admin_headers = await make_manage_headers(email="admin20@example.com")
    assessment = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=admin_headers
    )
    assessment_id = assessment.json()["id"]
    created = await client.post(
        "/grades",
        json=make_grade_payload(assessment_id, own_student.id),
        headers=admin_headers,
    )
    grade_id = created.json()["id"]

    response = await client.get(f"/grades/{grade_id}", headers=own_student_headers)

    assert response.status_code == 200
    assert response.json()["id"] == grade_id


async def test_get_grade_by_id_as_different_student_returns_404(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_student_with_headers: Callable[..., Awaitable[tuple[Student, dict[str, str]]]],
    make_class_instance: Callable[..., Awaitable[Class]],
    make_enrollment: Callable[..., Awaitable[Enrollment]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    klass = await make_class_instance()
    grade_owner = await make_student()
    other_student, other_student_headers = await make_student_with_headers()
    await make_enrollment(grade_owner.id, klass.id, status=EnrollmentStatus.ACTIVE)
    admin_headers = await make_manage_headers(email="admin21@example.com")
    assessment = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=admin_headers
    )
    assessment_id = assessment.json()["id"]
    created = await client.post(
        "/grades",
        json=make_grade_payload(assessment_id, grade_owner.id),
        headers=admin_headers,
    )
    grade_id = created.json()["id"]

    response = await client.get(f"/grades/{grade_id}", headers=other_student_headers)

    assert response.status_code == 404


async def test_get_grade_by_id_as_admin_happy_path(
    client: AsyncClient,
    enrolled_setup: tuple[Student, Class],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    student, klass = enrolled_setup
    headers = await make_manage_headers(email="admin22@example.com")
    assessment = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=headers
    )
    assessment_id = assessment.json()["id"]
    created = await client.post(
        "/grades", json=make_grade_payload(assessment_id, student.id), headers=headers
    )
    grade_id = created.json()["id"]

    response = await client.get(f"/grades/{grade_id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == grade_id


async def test_get_grade_by_id_as_teacher_who_owns_class_succeeds(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_class_for_teacher: Callable[..., Awaitable[Class]],
    make_enrollment: Callable[..., Awaitable[Enrollment]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
    make_teacher_with_headers: Callable[..., Awaitable[tuple[Teacher, dict[str, str]]]],
) -> None:
    teacher, teacher_headers = await make_teacher_with_headers()
    owned_class = await make_class_for_teacher(teacher.id)
    student = await make_student()
    await make_enrollment(student.id, owned_class.id, status=EnrollmentStatus.ACTIVE)
    admin_headers = await make_manage_headers(email="admin-grade-get-own@example.com")
    assessment = await client.post(
        "/assessments", json=make_assessment_payload(owned_class.id), headers=admin_headers
    )
    created = await client.post(
        "/grades",
        json=make_grade_payload(assessment.json()["id"], student.id),
        headers=admin_headers,
    )
    grade_id = created.json()["id"]

    response = await client.get(f"/grades/{grade_id}", headers=teacher_headers)

    assert response.status_code == 200
    assert response.json()["id"] == grade_id


async def test_get_grade_by_id_as_teacher_not_owning_class_returns_403(
    client: AsyncClient,
    enrolled_setup: tuple[Student, Class],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
    make_teacher_with_headers: Callable[..., Awaitable[tuple[Teacher, dict[str, str]]]],
) -> None:
    student, klass = enrolled_setup  # klass is owned by an unrelated teacher
    admin_headers = await make_manage_headers(email="admin-grade-get-notown@example.com")
    assessment = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=admin_headers
    )
    created = await client.post(
        "/grades",
        json=make_grade_payload(assessment.json()["id"], student.id),
        headers=admin_headers,
    )
    grade_id = created.json()["id"]
    _teacher, teacher_headers = await make_teacher_with_headers()

    response = await client.get(f"/grades/{grade_id}", headers=teacher_headers)

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /grades/{id}
# ---------------------------------------------------------------------------


async def test_patch_grade_happy_path(
    client: AsyncClient,
    enrolled_setup: tuple[Student, Class],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    student, klass = enrolled_setup
    headers = await make_manage_headers(email="admin23@example.com")
    assessment = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=headers
    )
    assessment_id = assessment.json()["id"]
    created = await client.post(
        "/grades", json=make_grade_payload(assessment_id, student.id), headers=headers
    )
    grade_id = created.json()["id"]

    response = await client.patch(
        f"/grades/{grade_id}", json={"score": "92.00"}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["score"] == "92.00"

    follow_up = await client.get(f"/grades/{grade_id}", headers=headers)
    assert follow_up.json()["score"] == "92.00"


async def test_patch_grade_score_exceeds_max_score_returns_409(
    client: AsyncClient,
    enrolled_setup: tuple[Student, Class],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    student, klass = enrolled_setup
    headers = await make_manage_headers(email="admin24@example.com")
    assessment = await client.post(
        "/assessments",
        json=make_assessment_payload(klass.id, max_score="50.00"),
        headers=headers,
    )
    assessment_id = assessment.json()["id"]
    created = await client.post(
        "/grades",
        json=make_grade_payload(assessment_id, student.id, score="30.00"),
        headers=headers,
    )
    grade_id = created.json()["id"]

    response = await client.patch(
        f"/grades/{grade_id}", json={"score": "75.00"}, headers=headers
    )

    assert response.status_code == 409


async def test_patch_grade_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin25@example.com")

    response = await client.patch(
        f"/grades/{uuid4()}", json={"score": "10.00"}, headers=headers
    )

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_patch_grade_as_student_role_returns_403(
    client: AsyncClient,
    enrolled_setup: tuple[Student, Class],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    student, klass = enrolled_setup
    admin_headers = await make_manage_headers(email="admin26@example.com")
    assessment = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=admin_headers
    )
    assessment_id = assessment.json()["id"]
    created = await client.post(
        "/grades",
        json=make_grade_payload(assessment_id, student.id),
        headers=admin_headers,
    )
    grade_id = created.json()["id"]
    student_headers = await make_manage_headers(
        role=UserRole.STUDENT, email="student4@example.com"
    )

    response = await client.patch(
        f"/grades/{grade_id}", json={"score": "10.00"}, headers=student_headers
    )

    assert response.status_code == 403


async def test_patch_grade_as_teacher_who_owns_class_succeeds(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_class_for_teacher: Callable[..., Awaitable[Class]],
    make_enrollment: Callable[..., Awaitable[Enrollment]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
    make_teacher_with_headers: Callable[..., Awaitable[tuple[Teacher, dict[str, str]]]],
) -> None:
    teacher, teacher_headers = await make_teacher_with_headers()
    owned_class = await make_class_for_teacher(teacher.id)
    student = await make_student()
    await make_enrollment(student.id, owned_class.id, status=EnrollmentStatus.ACTIVE)
    admin_headers = await make_manage_headers(email="admin-grade-patch-own@example.com")
    assessment = await client.post(
        "/assessments", json=make_assessment_payload(owned_class.id), headers=admin_headers
    )
    created = await client.post(
        "/grades",
        json=make_grade_payload(assessment.json()["id"], student.id),
        headers=admin_headers,
    )
    grade_id = created.json()["id"]

    response = await client.patch(
        f"/grades/{grade_id}", json={"score": "92.00"}, headers=teacher_headers
    )

    assert response.status_code == 200
    assert response.json()["score"] == "92.00"


async def test_patch_grade_as_teacher_not_owning_class_returns_403(
    client: AsyncClient,
    enrolled_setup: tuple[Student, Class],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
    make_teacher_with_headers: Callable[..., Awaitable[tuple[Teacher, dict[str, str]]]],
) -> None:
    student, klass = enrolled_setup  # klass is owned by an unrelated teacher
    admin_headers = await make_manage_headers(email="admin-grade-patch-notown@example.com")
    assessment = await client.post(
        "/assessments", json=make_assessment_payload(klass.id), headers=admin_headers
    )
    created = await client.post(
        "/grades",
        json=make_grade_payload(assessment.json()["id"], student.id),
        headers=admin_headers,
    )
    grade_id = created.json()["id"]
    _teacher, teacher_headers = await make_teacher_with_headers()

    response = await client.patch(
        f"/grades/{grade_id}", json={"score": "10.00"}, headers=teacher_headers
    )

    assert response.status_code == 403
