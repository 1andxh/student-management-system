from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.config import settings
from sms.db.session import get_db
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
