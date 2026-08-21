import secrets
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError

from sms.core import file_storage
from sms.core.config import settings
from sms.core.security import hash_password
from sms.domains.students.exceptions import (
    StudentAlreadyExistsError,
    StudentHasNoLinkedRecordError,
    StudentNotFoundError,
)
from sms.domains.students.models import EnrollmentStatus, Student
from sms.domains.students.repository import StudentRepository
from sms.domains.students.schemas import StudentCreate, StudentCredentialsRead, StudentUpdate
from sms.domains.users.exceptions import UserNotFoundError
from sms.domains.users.models import User, UserRole
from sms.domains.users.repository import UserRepository


def _format_student_number(n: int) -> str:
    return f"STU-{n:04d}"


class StudentService:
    def __init__(self, repository: StudentRepository, user_repository: UserRepository) -> None:
        self._repository = repository
        self._users = user_repository

    async def create(self, data: StudentCreate) -> Student:
        student_number = data.student_number
        if student_number is None:
            student_number = _format_student_number(
                await self._repository.next_student_number_seq()
            )

        if await self._repository.get_by_email(data.email) is not None:
            raise StudentAlreadyExistsError()
        if await self._repository.get_by_student_number(student_number) is not None:
            raise StudentAlreadyExistsError()
        if data.user_id is not None:
            if await self._repository.get_by_user_id(data.user_id) is not None:
                raise StudentAlreadyExistsError()
            await self._require_student_role_user(data.user_id)

        student = Student(
            student_number=student_number,
            first_name=data.first_name,
            last_name=data.last_name,
            date_of_birth=data.date_of_birth,
            email=data.email,
            guardian_name=data.guardian_name,
            guardian_phone=data.guardian_phone,
            enrollment_status=EnrollmentStatus.ACTIVE,
            user_id=data.user_id,
        )
        try:
            return await self._repository.add(student)
        except IntegrityError as exc:
            # The pre-checks above narrow the window but don't close it — a
            # concurrent request can still slip past both and hit the unique
            # constraint at commit time. That constraint is the actual
            # guard; this just translates its failure into the same domain
            # error instead of letting it surface as a raw 500.
            raise StudentAlreadyExistsError() from exc

    async def _require_student_role_user(self, user_id: UUID) -> None:
        # A student row's user_id is what login_with_pin trusts to decide
        # who a PIN authenticates as — linking it to a non-STUDENT account
        # (e.g. an ADMIN's) would let a routine PIN issuance/reset on this
        # student hand out that other account's session. Caught here, at
        # the point user_id is set, not just at login time.
        target = await self._users.get(user_id)
        if target is None or target.role != UserRole.STUDENT:
            raise UserNotFoundError()

    async def get(self, student_id: UUID) -> Student:
        student = await self._repository.get(student_id)
        if student is None:
            raise StudentNotFoundError()
        return student

    async def list(self, *, limit: int, offset: int) -> tuple[list[Student], int]:
        return await self._repository.list(limit=limit, offset=offset)

    async def update(self, student_id: UUID, data: StudentUpdate) -> Student:
        student = await self.get(student_id)
        updates = data.model_dump(exclude_unset=True)

        # Pre-checks for every uniqueness field, not just the one this
        # stage is adding (user_id) — matching the fix already established
        # for Teacher (docs/adr/0014): the DB constraint alone isn't
        # exercised by the in-memory unit-test fake, only by a real DB.
        new_email = updates.get("email")
        if new_email is not None and new_email != student.email:
            existing = await self._repository.get_by_email(new_email)
            if existing is not None and existing.id != student_id:
                raise StudentAlreadyExistsError()

        new_number = updates.get("student_number")
        if new_number is not None and new_number != student.student_number:
            existing = await self._repository.get_by_student_number(new_number)
            if existing is not None and existing.id != student_id:
                raise StudentAlreadyExistsError()

        new_user_id = updates.get("user_id")
        if new_user_id is not None and new_user_id != student.user_id:
            existing = await self._repository.get_by_user_id(new_user_id)
            if existing is not None and existing.id != student_id:
                raise StudentAlreadyExistsError()
            await self._require_student_role_user(new_user_id)

        for field, value in updates.items():
            setattr(student, field, value)
        try:
            return await self._repository.add(student)
        except IntegrityError as exc:
            raise StudentAlreadyExistsError() from exc

    async def delete(self, student_id: UUID) -> None:
        student = await self.get(student_id)
        if student.profile_picture_path is not None:
            Path(settings.upload_dir, student.profile_picture_path).unlink(missing_ok=True)
        await self._repository.remove(student)

    async def get_my_student(self, user_id: UUID) -> Student:
        student = await self._repository.get_by_user_id(user_id)
        if student is None:
            raise StudentHasNoLinkedRecordError()
        return student

    async def generate_pin(self, student_id: UUID) -> StudentCredentialsRead:
        student = await self.get(student_id)

        if student.user_id is None:
            # Same uniqueness pre-check UserService.create() itself runs —
            # without it, a colliding email surfaces as a raw IntegrityError
            # here instead of a clean, expected conflict.
            if await self._users.get_by_email(student.email) is not None:
                raise StudentAlreadyExistsError()

            # Random, immediately-discarded secret — NEVER
            # DUMMY_PASSWORD_HASH (that's a fixed, source-controlled hash;
            # reusing it as a real stored credential would let anyone
            # reading the source log in as this account). This just makes
            # the email+password path a structural dead end for a
            # PIN-only account, which is correct: nobody chose this
            # "password," so nobody should be able to use it.
            unusable_password_hash = hash_password(secrets.token_urlsafe(32))
            user = User(
                email=student.email,
                hashed_password=unusable_password_hash,
                role=UserRole.STUDENT,
                is_active=True,
            )
            try:
                created_user = await self._users.add(user, commit=False)
                student.user_id = created_user.id
                await self._repository.add(student, commit=False)
                await self._repository.commit()
            except Exception:
                await self._repository.rollback()
                raise

        pin = f"{secrets.randbelow(1_000_000):06d}"
        student.pin_hash = hash_password(pin)
        await self._repository.add(student)

        return StudentCredentialsRead(student_number=student.student_number, pin=pin)

    async def upload_profile_picture(self, student_id: UUID, file: UploadFile) -> Student:
        student = await self.get(student_id)
        path = await file_storage.save_profile_picture(
            file, subdir="students", entity_id=student.id
        )
        student.profile_picture_path = path
        return await self._repository.add(student)
