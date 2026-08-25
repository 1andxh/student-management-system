from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.config import settings
from sms.db.session import get_db
from sms.domains.academic_years.models import AcademicYear, Term
from sms.domains.classes.models import Class, Subject
from sms.domains.teachers.models import Teacher
from sms.domains.users.models import User, UserRole
from sms.main import create_app


def make_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
        "hire_date": "2020-01-01",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def make_teacher(db_session: AsyncSession):
    """Local factory fixture — only this file creates Teachers directly via
    the DB, so it isn't promoted to the shared conftest.py yet."""

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
def make_manage_headers(
    make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
):
    """Auth header for a user with the given role — admin by default, since
    most of these tests exercise the "can manage" path; pass
    role=UserRole.TEACHER to exercise the "authenticated but not allowed to
    mutate" path instead (teachers is ADMIN-only, stricter than students)."""

    async def _make_headers(role: UserRole = UserRole.ADMIN, **overrides: object) -> dict[str, str]:
        user = await make_user(role=role, **overrides)
        return auth_headers(user)

    return _make_headers


@pytest.fixture
async def client_with_uploads(db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Same shape as conftest.py's shared `client` fixture, but with
    settings.upload_dir monkeypatched to a pytest tmp_path *before*
    create_app() runs — main.py mounts StaticFiles(directory=
    settings.upload_dir) at app-creation time, so the patch has to land
    before that call, not just before the request. Mirrors
    tests/domains/students/integration/test_router.py's fixture of the
    same name."""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Local factory fixtures for the credentials/me-classes tests below —
# Subject/AcademicYear/Term/Class all belong to other domains, so these are
# direct-DB local duplicates, same convention as
# tests/domains/enrollments/integration/test_router.py and
# tests/domains/assessments/integration/test_router.py.
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
def make_class_for_teacher(
    make_subject: Callable[..., Awaitable[Subject]],
    make_term: Callable[..., Awaitable[Term]],
    make_class: Callable[..., Awaitable[Class]],
):
    """Like make_class, but only needs a teacher_id (builds its own
    Subject/Term) — used for GET /teachers/me/classes's happy path. Mirrors
    tests/domains/assessments/integration/test_router.py's fixture of the
    same name."""

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
    user via user_id — needed for GET /teachers/me/classes, since
    TeacherService.get_my_classes resolves "my own teacher record" via
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


async def test_post_teachers_happy_path(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin1@example.com")

    response = await client.post("/teachers", json=make_payload(), headers=headers)

    assert response.status_code == 201
    body = response.json()
    assert body["first_name"] == "Ada"
    assert body["last_name"] == "Lovelace"
    assert body["email"] == "ada@example.com"
    assert body["hire_date"] == "2020-01-01"
    assert body["user_id"] is None
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


async def test_post_teachers_duplicate_email_returns_409(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin2@example.com")

    await client.post(
        "/teachers", json=make_payload(email="dup@example.com"), headers=headers
    )

    response = await client.post(
        "/teachers", json=make_payload(email="dup@example.com"), headers=headers
    )

    assert response.status_code == 409


async def test_post_teachers_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.post("/teachers", json=make_payload())

    assert response.status_code == 401


async def test_post_teachers_as_teacher_role_returns_403(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher1@example.com")

    response = await client.post("/teachers", json=make_payload(), headers=headers)

    assert response.status_code == 403


async def test_get_teachers_list(
    client: AsyncClient,
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    await make_teacher(email="one@example.com")
    await make_teacher(email="two@example.com")
    # A teacher-role account can read even though it can't mutate — proves
    # the read path is gated on "authenticated", not "admin".
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher2@example.com")

    response = await client.get("/teachers", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 2
    assert {t["email"] for t in body} == {"one@example.com", "two@example.com"}


async def test_get_teachers_list_pagination_smoke(
    client: AsyncClient,
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    for i in range(3):
        await make_teacher(email=f"pgsmoke{i}@example.com")
    headers = await make_manage_headers(email="admin-pg-smoke@example.com")

    response = await client.get("/teachers", params={"limit": 2, "offset": 0}, headers=headers)

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.headers["X-Total-Count"] == "3"


async def test_get_teachers_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/teachers")

    assert response.status_code == 401


async def test_get_teacher_by_id_happy_path(
    client: AsyncClient,
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    teacher = await make_teacher()
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher3@example.com")

    response = await client.get(f"/teachers/{teacher.id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(teacher.id)
    assert body["email"] == teacher.email


async def test_get_teacher_by_id_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin3@example.com")

    response = await client.get(f"/teachers/{uuid4()}", headers=headers)

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_patch_teacher_happy_path(
    client: AsyncClient,
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    teacher = await make_teacher()
    headers = await make_manage_headers(email="admin4@example.com")

    response = await client.patch(
        f"/teachers/{teacher.id}", json={"first_name": "Grace-Updated"}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(teacher.id)
    assert body["first_name"] == "Grace-Updated"
    assert body["last_name"] == teacher.last_name


async def test_patch_teacher_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin5@example.com")

    response = await client.patch(
        f"/teachers/{uuid4()}", json={"first_name": "Nobody"}, headers=headers
    )

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_patch_teacher_as_teacher_role_returns_403(
    client: AsyncClient,
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    teacher = await make_teacher()
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher4@example.com")

    response = await client.patch(
        f"/teachers/{teacher.id}", json={"first_name": "Nope"}, headers=headers
    )

    assert response.status_code == 403


async def test_delete_teacher_happy_path(
    client: AsyncClient,
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    teacher = await make_teacher()
    headers = await make_manage_headers(email="admin6@example.com")

    response = await client.delete(f"/teachers/{teacher.id}", headers=headers)

    assert response.status_code == 204

    follow_up = await client.get(f"/teachers/{teacher.id}", headers=headers)
    assert follow_up.status_code == 404


async def test_delete_teacher_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin7@example.com")

    response = await client.delete(f"/teachers/{uuid4()}", headers=headers)

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_delete_teacher_as_teacher_role_returns_403(
    client: AsyncClient,
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    teacher = await make_teacher()
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher5@example.com")

    response = await client.delete(f"/teachers/{teacher.id}", headers=headers)

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# POST /teachers/{teacher_id}/profile-picture
# ---------------------------------------------------------------------------


async def test_post_teacher_profile_picture_happy_path(
    client_with_uploads: AsyncClient,
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    teacher = await make_teacher(email="pfp1@example.com")
    headers = await make_manage_headers(email="admin-pfp1@example.com")

    response = await client_with_uploads.post(
        f"/teachers/{teacher.id}/profile-picture",
        files={"file": ("photo.jpg", b"\xff\xd8\xfffake-jpeg-body", "image/jpeg")},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["profile_picture_path"] == f"teachers/{teacher.id}.jpg"


async def test_post_teacher_profile_picture_wrong_content_type_returns_415(
    client_with_uploads: AsyncClient,
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    teacher = await make_teacher(email="pfp2@example.com")
    headers = await make_manage_headers(email="admin-pfp2@example.com")

    response = await client_with_uploads.post(
        f"/teachers/{teacher.id}/profile-picture",
        files={"file": ("doc.pdf", b"not an image", "application/pdf")},
        headers=headers,
    )

    assert response.status_code == 415


async def test_post_teacher_profile_picture_as_teacher_role_returns_403(
    client_with_uploads: AsyncClient,
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    teacher = await make_teacher(email="pfp3@example.com")
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher-pfp3@example.com")

    response = await client_with_uploads.post(
        f"/teachers/{teacher.id}/profile-picture",
        files={"file": ("photo.jpg", b"\xff\xd8\xfffake-jpeg-body", "image/jpeg")},
        headers=headers,
    )

    assert response.status_code == 403


async def test_post_teacher_profile_picture_missing_teacher_returns_404(
    client_with_uploads: AsyncClient,
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    headers = await make_manage_headers(email="admin-pfp4@example.com")

    response = await client_with_uploads.post(
        f"/teachers/{uuid4()}/profile-picture",
        files={"file": ("photo.jpg", b"\xff\xd8\xfffake-jpeg-body", "image/jpeg")},
        headers=headers,
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /teachers/{teacher_id}/credentials
# ---------------------------------------------------------------------------


async def test_post_credentials_first_issuance_happy_path_and_password_logs_in(
    client: AsyncClient,
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    teacher = await make_teacher(email="cred1@example.com")
    headers = await make_manage_headers(email="admin-cred1@example.com")

    response = await client.post(f"/teachers/{teacher.id}/credentials", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "cred1@example.com"
    assert len(body["password"]) > 0

    # The issued password must actually work against the existing,
    # role-agnostic POST /auth/login (no auth-domain changes this stage).
    login_response = await client.post(
        "/auth/login", json={"email": "cred1@example.com", "password": body["password"]}
    )
    assert login_response.status_code == 200
    assert login_response.json()["access_token"]


async def test_post_credentials_first_issuance_creates_exactly_one_linked_user(
    client: AsyncClient,
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    teacher = await make_teacher(email="cred-linkcheck@example.com")
    headers = await make_manage_headers(email="admin-cred-linkcheck@example.com")

    response = await client.post(f"/teachers/{teacher.id}/credentials", headers=headers)
    assert response.status_code == 200

    follow_up = await client.get(f"/teachers/{teacher.id}", headers=headers)
    assert follow_up.status_code == 200
    assert follow_up.json()["user_id"] is not None


async def test_post_credentials_reissuance_resets_password_without_second_user(
    client: AsyncClient,
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    teacher = await make_teacher(email="cred2@example.com")
    headers = await make_manage_headers(email="admin-cred2@example.com")
    first = await client.post(f"/teachers/{teacher.id}/credentials", headers=headers)
    first_user_id = (await client.get(f"/teachers/{teacher.id}", headers=headers)).json()[
        "user_id"
    ]

    second = await client.post(f"/teachers/{teacher.id}/credentials", headers=headers)

    assert second.status_code == 200
    assert second.json()["email"] == "cred2@example.com"
    assert second.json()["password"] != first.json()["password"]
    second_user_id = (await client.get(f"/teachers/{teacher.id}", headers=headers)).json()[
        "user_id"
    ]
    assert second_user_id == first_user_id  # same linked User, not a new one

    # The reset password logs in; the old one no longer does.
    old_login = await client.post(
        "/auth/login", json={"email": "cred2@example.com", "password": first.json()["password"]}
    )
    assert old_login.status_code == 401
    new_login = await client.post(
        "/auth/login", json={"email": "cred2@example.com", "password": second.json()["password"]}
    )
    assert new_login.status_code == 200


async def test_post_credentials_email_collision_returns_409(
    client: AsyncClient,
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_user: Callable[..., Awaitable[User]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    teacher = await make_teacher(email="collide@example.com")
    # A pre-existing User with the same email, unrelated to this teacher —
    # first-issuance must not silently overwrite or reuse it.
    await make_user(email="collide@example.com")
    headers = await make_manage_headers(email="admin-cred-collide@example.com")

    response = await client.post(f"/teachers/{teacher.id}/credentials", headers=headers)

    assert response.status_code == 409


async def test_post_credentials_as_non_admin_returns_403(
    client: AsyncClient,
    make_teacher: Callable[..., Awaitable[Teacher]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    teacher = await make_teacher(email="cred-nonadmin@example.com")
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher-cred-nonadmin@example.com")

    response = await client.post(f"/teachers/{teacher.id}/credentials", headers=headers)

    assert response.status_code == 403


async def test_post_credentials_missing_teacher_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin-cred-missing@example.com")

    response = await client.post(f"/teachers/{uuid4()}/credentials", headers=headers)

    assert response.status_code == 404


async def test_post_credentials_without_token_returns_401(
    client: AsyncClient, make_teacher: Callable[..., Awaitable[Teacher]]
) -> None:
    teacher = await make_teacher(email="cred-notoken@example.com")

    response = await client.post(f"/teachers/{teacher.id}/credentials")

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /teachers/me/classes
# ---------------------------------------------------------------------------


async def test_get_my_classes_happy_path_returns_only_own_classes(
    client: AsyncClient,
    make_class_for_teacher: Callable[..., Awaitable[Class]],
    make_teacher_with_headers: Callable[..., Awaitable[tuple[Teacher, dict[str, str]]]],
) -> None:
    teacher, teacher_headers = await make_teacher_with_headers()
    owned_class = await make_class_for_teacher(teacher.id, room="Owned Room")
    # Someone else's class, owned by a different (unlinked) teacher — must
    # not appear in the response.
    _other_teacher, _other_headers = await make_teacher_with_headers()
    other_class = await make_class_for_teacher(_other_teacher.id, room="Other Room")

    response = await client.get("/teachers/me/classes", headers=teacher_headers)

    assert response.status_code == 200
    body = response.json()
    ids = {c["id"] for c in body}
    assert str(owned_class.id) in ids
    assert str(other_class.id) not in ids


async def test_get_my_classes_no_owned_classes_returns_empty_list(
    client: AsyncClient,
    make_teacher_with_headers: Callable[..., Awaitable[tuple[Teacher, dict[str, str]]]],
) -> None:
    _teacher, teacher_headers = await make_teacher_with_headers()

    response = await client.get("/teachers/me/classes", headers=teacher_headers)

    assert response.status_code == 200
    assert response.json() == []


async def test_get_my_classes_no_linked_teacher_record_returns_404(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = await make_user(role=UserRole.TEACHER, email="orphan-teacher-me-classes@example.com")
    headers = auth_headers(user)

    response = await client.get("/teachers/me/classes", headers=headers)

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_get_my_classes_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/teachers/me/classes")

    assert response.status_code == 401
