from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from sms.domains.academic_years.models import AcademicYear, Term
from sms.domains.assessments.models import Assessment, AssessmentType, Grade
from sms.domains.classes.models import Class, Subject
from sms.domains.enrollments.models import Enrollment, EnrollmentStatus
from sms.domains.students.models import Student
from sms.domains.teachers.models import Teacher
from sms.domains.users.models import User, UserRole


def make_subject_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {"name": "Mathematics", "code": "MATH101"}
    payload.update(overrides)
    return payload


def make_class_payload(
    subject_id: object, term_id: object, teacher_id: object, **overrides: object
) -> dict[str, object]:
    payload: dict[str, object] = {
        "subject_id": str(subject_id),
        "term_id": str(term_id),
        "teacher_id": str(teacher_id),
        "capacity": 30,
        "room": "Room 101",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def make_subject(db_session: AsyncSession):
    """Local factory fixture — creates a Subject directly via the DB."""

    async def _make_subject(**overrides: object) -> Subject:
        defaults: dict[str, object] = {"name": "Mathematics", "code": "MATH101"}
        defaults.update(overrides)
        subject = Subject(**defaults)
        db_session.add(subject)
        await db_session.commit()
        await db_session.refresh(subject)
        return subject

    return _make_subject


@pytest.fixture
def make_academic_year(db_session: AsyncSession):
    """Local factory fixture — creates an AcademicYear directly via the DB,
    needed as a parent for make_term (a Class references a Term, and a Term
    requires an AcademicYear)."""

    async def _make_academic_year(**overrides: object) -> AcademicYear:
        defaults: dict[str, object] = {
            "name": "2024-2025",
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
def make_term(db_session: AsyncSession, make_academic_year: Callable[..., Awaitable[AcademicYear]]):
    """Local factory fixture — creates a Term directly via the DB, creating
    its own parent AcademicYear if academic_year_id isn't passed
    explicitly, since classes tests only care about the Term existing."""

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
    """Local factory fixture — creates a Teacher directly via the DB."""

    async def _make_teacher(**overrides: object) -> Teacher:
        defaults: dict[str, object] = {
            "first_name": "Grace",
            "last_name": "Hopper",
            "email": "grace@example.com",
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
    """Local factory fixture — creates a Class directly via the DB, tied to
    already-created Subject/Term/Teacher (pass their ids explicitly)."""

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
def make_manage_headers(
    make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
):
    """Auth header for a user with the given role — admin by default, since
    most of these tests exercise the "can manage" path; pass
    role=UserRole.TEACHER to exercise the "authenticated but not allowed to
    mutate" path instead (subjects/classes are ADMIN-only for writes, same
    tier as teachers and academic-years)."""

    async def _make_headers(role: UserRole = UserRole.ADMIN, **overrides: object) -> dict[str, str]:
        user = await make_user(role=role, **overrides)
        return auth_headers(user)

    return _make_headers


# ---------------------------------------------------------------------------
# Local factory fixtures for the /classes/{class_id}/gradebook tests below —
# Student/Enrollment/Assessment/Grade all belong to other domains, so these
# are direct-DB local duplicates (not imports), same convention as
# tests/domains/enrollments/integration/test_router.py's Subject/Term/
# Teacher/Class fixtures.
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
def make_assessment(db_session: AsyncSession):
    async def _make_assessment(class_id: object, **overrides: object) -> Assessment:
        defaults: dict[str, object] = {
            "class_id": class_id,
            "name": "Midterm Exam",
            "type": AssessmentType.EXAM,
            "max_score": Decimal("100.00"),
            "date": date(2024, 10, 15),
        }
        defaults.update(overrides)
        assessment = Assessment(**defaults)
        db_session.add(assessment)
        await db_session.commit()
        await db_session.refresh(assessment)
        return assessment

    return _make_assessment


@pytest.fixture
def make_grade(db_session: AsyncSession):
    async def _make_grade(assessment_id: object, student_id: object, **overrides: object) -> Grade:
        defaults: dict[str, object] = {
            "assessment_id": assessment_id,
            "student_id": student_id,
            "score": Decimal("85.00"),
        }
        defaults.update(overrides)
        grade = Grade(**defaults)
        db_session.add(grade)
        await db_session.commit()
        await db_session.refresh(grade)
        return grade

    return _make_grade


@pytest.fixture
def make_class_for_teacher(
    make_subject: Callable[..., Awaitable[Subject]],
    make_term: Callable[..., Awaitable[Term]],
    make_class: Callable[..., Awaitable[Class]],
):
    """Like make_class, but only needs a teacher_id (builds its own
    Subject/Term) — used for the TEACHER class-ownership scoping tests.
    Mirrors tests/domains/assessments/integration/test_router.py's fixture
    of the same name."""

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
    """Creates a User (role=TEACHER) AND a Teacher record linked to that same
    user via user_id — needed for the gradebook's TEACHER class-ownership
    scoping tests, since GradeService resolves "my own teacher record" via
    TeacherRepository.get_by_user_id(current_user.id). Mirrors
    tests/domains/assessments/integration/test_router.py's fixture of the
    same name."""

    async def _make(**overrides: object) -> tuple[Teacher, dict[str, str]]:
        unique = uuid4().hex[:8]
        user_overrides: dict[str, object] = {"email": f"teacheruser{unique}@example.com"}
        user_overrides.update(overrides)
        user = await make_user(role=UserRole.TEACHER, **user_overrides)
        teacher = await make_teacher(user_id=user.id, email=f"teacherrec{unique}@example.com")
        return teacher, auth_headers(user)

    return _make


@pytest.fixture
def make_student_with_headers(
    make_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[User], dict[str, str]],
    make_student: Callable[..., Awaitable[Student]],
):
    """Creates a User (role=STUDENT) AND a Student record linked to that
    same user via user_id — needed for the "STUDENT gets 403 even for their
    own enrolled class" gradebook test. Mirrors
    tests/domains/assessments/integration/test_router.py's fixture of the
    same name."""

    async def _make(**overrides: object) -> tuple[Student, dict[str, str]]:
        unique = uuid4().hex[:8]
        user_overrides: dict[str, object] = {"email": f"student{unique}@example.com"}
        user_overrides.update(overrides)
        user = await make_user(role=UserRole.STUDENT, **user_overrides)
        student = await make_student(user_id=user.id)
        return student, auth_headers(user)

    return _make


# ---------------------------------------------------------------------------
# /subjects
# ---------------------------------------------------------------------------


async def test_post_subjects_happy_path(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin1@example.com")

    response = await client.post("/subjects", json=make_subject_payload(), headers=headers)

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Mathematics"
    assert body["code"] == "MATH101"
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


async def test_post_subjects_duplicate_code_returns_409(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin2@example.com")

    await client.post(
        "/subjects", json=make_subject_payload(code="DUP101"), headers=headers
    )

    response = await client.post(
        "/subjects", json=make_subject_payload(name="Other Subject", code="DUP101"), headers=headers
    )

    assert response.status_code == 409


async def test_post_subjects_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.post("/subjects", json=make_subject_payload())

    assert response.status_code == 401


async def test_post_subjects_as_teacher_role_returns_403(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher1@example.com")

    response = await client.post("/subjects", json=make_subject_payload(), headers=headers)

    assert response.status_code == 403


async def test_get_subjects_list(
    client: AsyncClient,
    make_subject: Callable[..., Awaitable[Subject]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    await make_subject(name="Mathematics", code="MATH101")
    await make_subject(name="Physics", code="PHYS101")
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher2@example.com")

    response = await client.get("/subjects", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 2
    assert {s["code"] for s in body} == {"MATH101", "PHYS101"}


async def test_get_subjects_list_pagination_smoke(
    client: AsyncClient,
    make_subject: Callable[..., Awaitable[Subject]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    for i in range(3):
        await make_subject(name=f"PG Subject {i}", code=f"PGCODE{i}")
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher-pg-subj@example.com")

    response = await client.get("/subjects", params={"limit": 2, "offset": 0}, headers=headers)

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.headers["X-Total-Count"] == "3"


async def test_get_subject_by_id_happy_path(
    client: AsyncClient,
    make_subject: Callable[..., Awaitable[Subject]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    subject = await make_subject()
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher3@example.com")

    response = await client.get(f"/subjects/{subject.id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(subject.id)
    assert body["code"] == subject.code


async def test_get_subject_by_id_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin3@example.com")

    response = await client.get(f"/subjects/{uuid4()}", headers=headers)

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_patch_subject_happy_path(
    client: AsyncClient,
    make_subject: Callable[..., Awaitable[Subject]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    subject = await make_subject()
    headers = await make_manage_headers(email="admin4@example.com")

    response = await client.patch(
        f"/subjects/{subject.id}", json={"name": "Advanced Math"}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(subject.id)
    assert body["name"] == "Advanced Math"


async def test_patch_subject_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin5@example.com")

    response = await client.patch(
        f"/subjects/{uuid4()}", json={"name": "Nobody"}, headers=headers
    )

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_patch_subject_as_teacher_role_returns_403(
    client: AsyncClient,
    make_subject: Callable[..., Awaitable[Subject]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    subject = await make_subject()
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher4@example.com")

    response = await client.patch(
        f"/subjects/{subject.id}", json={"name": "Nope"}, headers=headers
    )

    assert response.status_code == 403


async def test_delete_subject_happy_path(
    client: AsyncClient,
    make_subject: Callable[..., Awaitable[Subject]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    subject = await make_subject()
    headers = await make_manage_headers(email="admin6@example.com")

    response = await client.delete(f"/subjects/{subject.id}", headers=headers)

    assert response.status_code == 204

    follow_up = await client.get(f"/subjects/{subject.id}", headers=headers)
    assert follow_up.status_code == 404


async def test_delete_subject_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin7@example.com")

    response = await client.delete(f"/subjects/{uuid4()}", headers=headers)

    assert response.status_code == 404
    assert "detail" in response.json()


# ---------------------------------------------------------------------------
# /classes
# ---------------------------------------------------------------------------


async def test_post_classes_happy_path(
    client: AsyncClient,
    make_subject: Callable[..., Awaitable[Subject]],
    make_term: Callable[..., Awaitable[Term]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    subject = await make_subject()
    term = await make_term()
    teacher = await make_teacher()
    headers = await make_manage_headers(email="admin8@example.com")

    response = await client.post(
        "/classes", json=make_class_payload(subject.id, term.id, teacher.id), headers=headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["subject_id"] == str(subject.id)
    assert body["term_id"] == str(term.id)
    assert body["teacher_id"] == str(teacher.id)
    assert body["capacity"] == 30
    assert body["room"] == "Room 101"
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


async def test_post_classes_nonexistent_subject_returns_404(
    client: AsyncClient,
    make_term: Callable[..., Awaitable[Term]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    term = await make_term()
    teacher = await make_teacher()
    headers = await make_manage_headers(email="admin9@example.com")

    response = await client.post(
        "/classes", json=make_class_payload(uuid4(), term.id, teacher.id), headers=headers
    )

    assert response.status_code == 404


async def test_post_classes_nonexistent_term_returns_404(
    client: AsyncClient,
    make_subject: Callable[..., Awaitable[Subject]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    subject = await make_subject()
    teacher = await make_teacher()
    headers = await make_manage_headers(email="admin10@example.com")

    response = await client.post(
        "/classes", json=make_class_payload(subject.id, uuid4(), teacher.id), headers=headers
    )

    assert response.status_code == 404


async def test_post_classes_nonexistent_teacher_returns_404(
    client: AsyncClient,
    make_subject: Callable[..., Awaitable[Subject]],
    make_term: Callable[..., Awaitable[Term]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    subject = await make_subject()
    term = await make_term()
    headers = await make_manage_headers(email="admin11@example.com")

    response = await client.post(
        "/classes", json=make_class_payload(subject.id, term.id, uuid4()), headers=headers
    )

    assert response.status_code == 404


async def test_post_classes_zero_capacity_returns_422(
    client: AsyncClient,
    make_subject: Callable[..., Awaitable[Subject]],
    make_term: Callable[..., Awaitable[Term]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    subject = await make_subject()
    term = await make_term()
    teacher = await make_teacher()
    headers = await make_manage_headers(email="admin12@example.com")

    response = await client.post(
        "/classes",
        json=make_class_payload(subject.id, term.id, teacher.id, capacity=0),
        headers=headers,
    )

    assert response.status_code == 422


async def test_post_classes_without_token_returns_401(
    client: AsyncClient,
    make_subject: Callable[..., Awaitable[Subject]],
    make_term: Callable[..., Awaitable[Term]],
    make_teacher: Callable[..., Awaitable[Teacher]],
) -> None:
    subject = await make_subject()
    term = await make_term()
    teacher = await make_teacher()

    response = await client.post(
        "/classes", json=make_class_payload(subject.id, term.id, teacher.id)
    )

    assert response.status_code == 401


async def test_post_classes_as_teacher_role_returns_403(
    client: AsyncClient,
    make_subject: Callable[..., Awaitable[Subject]],
    make_term: Callable[..., Awaitable[Term]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    subject = await make_subject()
    term = await make_term()
    teacher = await make_teacher()
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher5@example.com")

    response = await client.post(
        "/classes", json=make_class_payload(subject.id, term.id, teacher.id), headers=headers
    )

    assert response.status_code == 403


async def test_get_classes_list(
    client: AsyncClient,
    make_subject: Callable[..., Awaitable[Subject]],
    make_term: Callable[..., Awaitable[Term]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_class: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    subject = await make_subject()
    term = await make_term()
    teacher = await make_teacher()
    await make_class(subject.id, term.id, teacher.id, room="A")
    await make_class(subject.id, term.id, teacher.id, room="B")
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher6@example.com")

    response = await client.get("/classes", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 2
    assert {c["room"] for c in body} == {"A", "B"}


async def test_get_classes_list_pagination_slices_and_sets_total_count_header(
    client: AsyncClient,
    make_subject: Callable[..., Awaitable[Subject]],
    make_term: Callable[..., Awaitable[Term]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_class: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    subject = await make_subject()
    term = await make_term()
    teacher = await make_teacher()
    for i in range(5):
        await make_class(subject.id, term.id, teacher.id, room=f"Room-PG-{i}")
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher-pg-class@example.com")

    response = await client.get("/classes", params={"limit": 2, "offset": 0}, headers=headers)

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.headers["X-Total-Count"] == "5"


async def test_get_classes_list_filtered_by_term_subject_teacher(
    client: AsyncClient,
    make_subject: Callable[..., Awaitable[Subject]],
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_term: Callable[..., Awaitable[Term]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_class: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    subject_a = await make_subject(name="Subject A", code="SUBA")
    subject_b = await make_subject(name="Subject B", code="SUBB")
    # Share one AcademicYear across both terms — make_term's default
    # academic_year_id creation uses a fixed literal name
    # (uq_academic_years_name-constrained), so two independent calls
    # without an explicit academic_year_id would collide.
    year = await make_academic_year(name="Filter Terms Year")
    term_a = await make_term(academic_year_id=year.id, name="Term Filter A")
    term_b = await make_term(
        academic_year_id=year.id,
        name="Term Filter B",
        start_date=date(2025, 1, 6),
        end_date=date(2025, 3, 30),
    )
    teacher_a = await make_teacher(email="filter-teacher-a@example.com")
    teacher_b = await make_teacher(email="filter-teacher-b@example.com")
    target = await make_class(subject_a.id, term_a.id, teacher_a.id, room="Target")
    await make_class(subject_b.id, term_a.id, teacher_a.id, room="OtherSubject")
    await make_class(subject_a.id, term_b.id, teacher_a.id, room="OtherTerm")
    await make_class(subject_a.id, term_a.id, teacher_b.id, room="OtherTeacher")
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher-filter@example.com")

    response = await client.get(
        "/classes",
        params={
            "term_id": str(term_a.id),
            "subject_id": str(subject_a.id),
            "teacher_id": str(teacher_a.id),
        },
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(target.id)


async def test_get_classes_list_newest_first_ordering(
    client: AsyncClient,
    make_subject: Callable[..., Awaitable[Subject]],
    make_term: Callable[..., Awaitable[Term]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_class: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    # Explicit, distinguishable created_at — db_session wraps the whole test
    # in one outer Postgres transaction (SAVEPOINT-based rollback, see
    # conftest.py); func.now()/CURRENT_TIMESTAMP is transaction-scoped, not
    # statement-scoped, so every row inserted in one test would otherwise
    # get an identical server-default created_at.
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    subject = await make_subject()
    term = await make_term()
    teacher = await make_teacher()
    first = await make_class(subject.id, term.id, teacher.id, room="Ord-A", created_at=base)
    second = await make_class(
        subject.id, term.id, teacher.id, room="Ord-B", created_at=base + timedelta(minutes=1)
    )
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher-ord-class@example.com")

    response = await client.get("/classes", headers=headers)

    assert response.status_code == 200
    ids = [c["id"] for c in response.json()]
    assert ids.index(str(second.id)) < ids.index(str(first.id))


async def test_get_classes_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/classes")

    assert response.status_code == 401


async def test_get_class_by_id_happy_path(
    client: AsyncClient,
    make_subject: Callable[..., Awaitable[Subject]],
    make_term: Callable[..., Awaitable[Term]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_class: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    subject = await make_subject()
    term = await make_term()
    teacher = await make_teacher()
    klass = await make_class(subject.id, term.id, teacher.id)
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher7@example.com")

    response = await client.get(f"/classes/{klass.id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(klass.id)
    assert body["subject_id"] == str(subject.id)


async def test_get_class_by_id_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin13@example.com")

    response = await client.get(f"/classes/{uuid4()}", headers=headers)

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_patch_class_happy_path(
    client: AsyncClient,
    make_subject: Callable[..., Awaitable[Subject]],
    make_term: Callable[..., Awaitable[Term]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_class: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    subject = await make_subject()
    term = await make_term()
    teacher = await make_teacher()
    klass = await make_class(subject.id, term.id, teacher.id)
    headers = await make_manage_headers(email="admin14@example.com")

    response = await client.patch(
        f"/classes/{klass.id}", json={"capacity": 45}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(klass.id)
    assert body["capacity"] == 45


async def test_patch_class_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin15@example.com")

    response = await client.patch(
        f"/classes/{uuid4()}", json={"capacity": 20}, headers=headers
    )

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_patch_class_as_teacher_role_returns_403(
    client: AsyncClient,
    make_subject: Callable[..., Awaitable[Subject]],
    make_term: Callable[..., Awaitable[Term]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_class: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    subject = await make_subject()
    term = await make_term()
    teacher = await make_teacher()
    klass = await make_class(subject.id, term.id, teacher.id)
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher8@example.com")

    response = await client.patch(
        f"/classes/{klass.id}", json={"capacity": 20}, headers=headers
    )

    assert response.status_code == 403


async def test_delete_class_happy_path(
    client: AsyncClient,
    make_subject: Callable[..., Awaitable[Subject]],
    make_term: Callable[..., Awaitable[Term]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_class: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    subject = await make_subject()
    term = await make_term()
    teacher = await make_teacher()
    klass = await make_class(subject.id, term.id, teacher.id)
    headers = await make_manage_headers(email="admin16@example.com")

    response = await client.delete(f"/classes/{klass.id}", headers=headers)

    assert response.status_code == 204

    follow_up = await client.get(f"/classes/{klass.id}", headers=headers)
    assert follow_up.status_code == 404


async def test_delete_class_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin17@example.com")

    response = await client.delete(f"/classes/{uuid4()}", headers=headers)

    assert response.status_code == 404
    assert "detail" in response.json()


# ---------------------------------------------------------------------------
# GET /classes/{class_id}/gradebook
# ---------------------------------------------------------------------------


async def test_get_gradebook_assembles_correct_columns_rows_and_scores(
    client: AsyncClient,
    make_subject: Callable[..., Awaitable[Subject]],
    make_term: Callable[..., Awaitable[Term]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_class: Callable[..., Awaitable[Class]],
    make_student: Callable[..., Awaitable[Student]],
    make_enrollment: Callable[..., Awaitable[Enrollment]],
    make_assessment: Callable[..., Awaitable[Assessment]],
    make_grade: Callable[..., Awaitable[Grade]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    subject = await make_subject()
    term = await make_term()
    teacher = await make_teacher()
    klass = await make_class(subject.id, term.id, teacher.id)
    # Dates deliberately out of insertion order — columns must come back
    # sorted by date ascending, not creation order.
    quiz = await make_assessment(
        klass.id, name="Quiz 1", date=date(2024, 9, 5), max_score=Decimal("20.00")
    )
    exam = await make_assessment(
        klass.id, name="Midterm", date=date(2024, 10, 15), max_score=Decimal("100.00")
    )
    # Last names deliberately out of insertion order — rows must come back
    # sorted by (last_name, first_name), not creation order.
    student_zephyr = await make_student(first_name="Amy", last_name="Zephyr")
    student_adams = await make_student(first_name="Ben", last_name="Adams")
    await make_enrollment(student_zephyr.id, klass.id, status=EnrollmentStatus.ACTIVE)
    await make_enrollment(student_adams.id, klass.id, status=EnrollmentStatus.ACTIVE)
    # student_adams graded on both; student_zephyr graded on the quiz only —
    # exercises both a real score and an explicit null (ungraded) entry.
    await make_grade(quiz.id, student_adams.id, score=Decimal("18.00"))
    await make_grade(exam.id, student_adams.id, score=Decimal("85.00"))
    await make_grade(quiz.id, student_zephyr.id, score=Decimal("15.00"))
    headers = await make_manage_headers(email="admin-gradebook1@example.com")

    response = await client.get(f"/classes/{klass.id}/gradebook", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["class_id"] == str(klass.id)
    assert [a["assessment_id"] for a in body["assessments"]] == [str(quiz.id), str(exam.id)]
    assert [a["name"] for a in body["assessments"]] == ["Quiz 1", "Midterm"]

    assert [s["student_id"] for s in body["students"]] == [
        str(student_adams.id),
        str(student_zephyr.id),
    ]

    adams_row = body["students"][0]
    assert adams_row["scores"] == {str(quiz.id): "18.00", str(exam.id): "85.00"}

    zephyr_row = body["students"][1]
    assert zephyr_row["scores"] == {str(quiz.id): "15.00", str(exam.id): None}


async def test_get_gradebook_dropped_student_excluded(
    client: AsyncClient,
    make_subject: Callable[..., Awaitable[Subject]],
    make_term: Callable[..., Awaitable[Term]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_class: Callable[..., Awaitable[Class]],
    make_student: Callable[..., Awaitable[Student]],
    make_enrollment: Callable[..., Awaitable[Enrollment]],
    make_assessment: Callable[..., Awaitable[Assessment]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    subject = await make_subject()
    term = await make_term()
    teacher = await make_teacher()
    klass = await make_class(subject.id, term.id, teacher.id)
    await make_assessment(klass.id)
    active_student = await make_student(email="active-dropcheck@example.com")
    dropped_student = await make_student(email="dropped-dropcheck@example.com")
    await make_enrollment(active_student.id, klass.id, status=EnrollmentStatus.ACTIVE)
    await make_enrollment(dropped_student.id, klass.id, status=EnrollmentStatus.DROPPED)
    headers = await make_manage_headers(email="admin-gradebook2@example.com")

    response = await client.get(f"/classes/{klass.id}/gradebook", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert [s["student_id"] for s in body["students"]] == [str(active_student.id)]


async def test_get_gradebook_missing_class_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin-gradebook3@example.com")

    response = await client.get(f"/classes/{uuid4()}/gradebook", headers=headers)

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_get_gradebook_without_token_returns_401(
    client: AsyncClient,
    make_subject: Callable[..., Awaitable[Subject]],
    make_term: Callable[..., Awaitable[Term]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_class: Callable[..., Awaitable[Class]],
) -> None:
    subject = await make_subject()
    term = await make_term()
    teacher = await make_teacher()
    klass = await make_class(subject.id, term.id, teacher.id)

    response = await client.get(f"/classes/{klass.id}/gradebook")

    assert response.status_code == 401


async def test_get_gradebook_as_teacher_who_owns_class_returns_200(
    client: AsyncClient,
    make_class_for_teacher: Callable[..., Awaitable[Class]],
    make_teacher_with_headers: Callable[..., Awaitable[tuple[Teacher, dict[str, str]]]],
) -> None:
    teacher, teacher_headers = await make_teacher_with_headers()
    owned_class = await make_class_for_teacher(teacher.id)

    response = await client.get(f"/classes/{owned_class.id}/gradebook", headers=teacher_headers)

    assert response.status_code == 200
    assert response.json()["class_id"] == str(owned_class.id)


async def test_get_gradebook_as_teacher_not_owning_class_returns_403(
    client: AsyncClient,
    make_subject: Callable[..., Awaitable[Subject]],
    make_term: Callable[..., Awaitable[Term]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_class: Callable[..., Awaitable[Class]],
    make_teacher_with_headers: Callable[..., Awaitable[tuple[Teacher, dict[str, str]]]],
) -> None:
    subject = await make_subject()
    term = await make_term()
    other_teacher = await make_teacher()
    klass = await make_class(subject.id, term.id, other_teacher.id)  # owned by another teacher
    _teacher, teacher_headers = await make_teacher_with_headers()

    response = await client.get(f"/classes/{klass.id}/gradebook", headers=teacher_headers)

    assert response.status_code == 403


async def test_get_gradebook_as_admin_succeeds_regardless_of_ownership(
    client: AsyncClient,
    make_class_for_teacher: Callable[..., Awaitable[Class]],
    make_teacher_with_headers: Callable[..., Awaitable[tuple[Teacher, dict[str, str]]]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    teacher, _teacher_headers = await make_teacher_with_headers()
    someone_elses_class = await make_class_for_teacher(teacher.id)
    admin_headers = await make_manage_headers(email="admin-gradebook-owner-check@example.com")

    response = await client.get(
        f"/classes/{someone_elses_class.id}/gradebook", headers=admin_headers
    )

    assert response.status_code == 200


async def test_get_gradebook_as_student_role_returns_403_even_for_own_enrolled_class(
    client: AsyncClient,
    make_subject: Callable[..., Awaitable[Subject]],
    make_term: Callable[..., Awaitable[Term]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_class: Callable[..., Awaitable[Class]],
    make_enrollment: Callable[..., Awaitable[Enrollment]],
    make_student_with_headers: Callable[..., Awaitable[tuple[Student, dict[str, str]]]],
) -> None:
    subject = await make_subject()
    term = await make_term()
    teacher = await make_teacher()
    klass = await make_class(subject.id, term.id, teacher.id)
    own_student, own_student_headers = await make_student_with_headers()
    await make_enrollment(own_student.id, klass.id, status=EnrollmentStatus.ACTIVE)

    response = await client.get(f"/classes/{klass.id}/gradebook", headers=own_student_headers)

    assert response.status_code == 403


async def test_patch_class_term_id_while_attached_to_section_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
    make_subject: Callable[..., Awaitable[Subject]],
    make_term: Callable[..., Awaitable[Term]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_class: Callable[..., Awaitable[Class]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    # A section-taught class is pinned to its section's academic year.
    # SectionService.attach_class validates that at attach time; without
    # this guard a later term change would silently move the class into a
    # different year, re-opening the mismatch (docs/adr/0024).
    from sms.domains.academic_years.models import AcademicYear
    from sms.domains.sections.models import GradeLevel, Section

    subject = await make_subject()
    term = await make_term()
    teacher = await make_teacher()
    klass = await make_class(subject.id, term.id, teacher.id)

    grade_level = GradeLevel(name=f"Grade {uuid4().hex[:6]}", rank=7)
    year = AcademicYear(
        name=f"Year {uuid4().hex[:8]}", start_date=date(2024, 9, 1), end_date=date(2025, 6, 30)
    )
    db_session.add_all([grade_level, year])
    await db_session.commit()
    section = Section(
        grade_level_id=grade_level.id,
        academic_year_id=year.id,
        name="A",
        capacity=30,
    )
    db_session.add(section)
    await db_session.commit()
    klass.section_id = section.id
    db_session.add(klass)
    await db_session.commit()

    # Same academic year, different term — make_academic_year uses a fixed
    # name, so a second call would collide on uq_academic_years_name. The
    # guard rejects any term change while attached, so this still exercises
    # it (and proves the rejection isn't merely a year comparison).
    other_term = await make_term(academic_year_id=term.academic_year_id, name="Term 2")
    headers = await make_manage_headers(email="admin-pinned-term@example.com")

    response = await client.patch(
        f"/classes/{klass.id}", json={"term_id": str(other_term.id)}, headers=headers
    )

    assert response.status_code == 409
