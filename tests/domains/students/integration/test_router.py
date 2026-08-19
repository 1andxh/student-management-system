from datetime import date
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from sms.domains.students.models import Student


def make_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "student_number": "S-1000",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "date_of_birth": "2010-01-01",
        "email": "ada@example.com",
        "guardian_name": "Byron Lovelace",
        "guardian_phone": "+1-555-0100",
    }
    payload.update(overrides)
    return payload


async def create_student_via_db(db_session: AsyncSession, **overrides: object) -> Student:
    defaults: dict[str, object] = {
        "student_number": "S-2000",
        "first_name": "Grace",
        "last_name": "Hopper",
        "date_of_birth": date(1906, 12, 9),
        "email": "grace@example.com",
        "guardian_name": "Walter Hopper",
        "guardian_phone": "+1-555-0200",
    }
    defaults.update(overrides)
    student = Student(**defaults)
    db_session.add(student)
    await db_session.commit()
    await db_session.refresh(student)
    return student


async def test_post_students_happy_path(client: AsyncClient) -> None:
    response = await client.post("/students", json=make_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["student_number"] == "S-1000"
    assert body["first_name"] == "Ada"
    assert body["last_name"] == "Lovelace"
    assert body["date_of_birth"] == "2010-01-01"
    assert body["email"] == "ada@example.com"
    assert body["guardian_name"] == "Byron Lovelace"
    assert body["guardian_phone"] == "+1-555-0100"
    assert body["enrollment_status"] == "active"
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


async def test_post_students_duplicate_email_returns_409(client: AsyncClient) -> None:
    await client.post(
        "/students", json=make_payload(student_number="S-1001", email="dup@example.com")
    )

    response = await client.post(
        "/students", json=make_payload(student_number="S-1002", email="dup@example.com")
    )

    assert response.status_code == 409


async def test_post_students_duplicate_student_number_returns_409(
    client: AsyncClient,
) -> None:
    await client.post(
        "/students", json=make_payload(student_number="S-DUP", email="one@example.com")
    )

    response = await client.post(
        "/students", json=make_payload(student_number="S-DUP", email="two@example.com")
    )

    assert response.status_code == 409


async def test_get_students_list(client: AsyncClient, db_session: AsyncSession) -> None:
    await create_student_via_db(db_session, student_number="S-3001", email="one@example.com")
    await create_student_via_db(db_session, student_number="S-3002", email="two@example.com")

    response = await client.get("/students")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 2
    assert {s["student_number"] for s in body} == {"S-3001", "S-3002"}


async def test_get_student_by_id_happy_path(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    student = await create_student_via_db(db_session)

    response = await client.get(f"/students/{student.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(student.id)
    assert body["email"] == student.email


async def test_get_student_by_id_missing_returns_404(client: AsyncClient) -> None:
    response = await client.get(f"/students/{uuid4()}")

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_patch_student_happy_path(client: AsyncClient, db_session: AsyncSession) -> None:
    student = await create_student_via_db(db_session)

    response = await client.patch(
        f"/students/{student.id}", json={"first_name": "Grace-Updated"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(student.id)
    assert body["first_name"] == "Grace-Updated"
    assert body["last_name"] == student.last_name


async def test_patch_student_missing_returns_404(client: AsyncClient) -> None:
    response = await client.patch(f"/students/{uuid4()}", json={"first_name": "Nobody"})

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_delete_student_happy_path(client: AsyncClient, db_session: AsyncSession) -> None:
    student = await create_student_via_db(db_session)

    response = await client.delete(f"/students/{student.id}")

    assert response.status_code == 204

    follow_up = await client.get(f"/students/{student.id}")
    assert follow_up.status_code == 404


async def test_delete_student_missing_returns_404(client: AsyncClient) -> None:
    response = await client.delete(f"/students/{uuid4()}")

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_post_students_missing_required_field_returns_422(client: AsyncClient) -> None:
    payload = make_payload()
    del payload["email"]

    response = await client.post("/students", json=payload)

    assert response.status_code == 422
    body = response.json()
    assert body["detail"] == "Validation failed."
    assert "errors" in body
