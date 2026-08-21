from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError

from sms.core import file_storage
from sms.core.config import settings
from sms.domains.teachers.exceptions import (
    ChangeRequestNotPendingError,
    PendingChangeRequestExistsError,
    TeacherAlreadyExistsError,
    TeacherChangeRequestNotFoundError,
    TeacherHasNoLinkedRecordError,
    TeacherNotFoundError,
)
from sms.domains.teachers.models import ChangeRequestStatus, Teacher, TeacherChangeRequest
from sms.domains.teachers.repository import TeacherChangeRequestRepository, TeacherRepository
from sms.domains.teachers.schemas import TeacherChangeRequestCreate, TeacherCreate, TeacherUpdate


class TeacherService:
    def __init__(self, repository: TeacherRepository) -> None:
        self._repository = repository

    async def create(self, data: TeacherCreate) -> Teacher:
        if await self._repository.get_by_email(data.email) is not None:
            raise TeacherAlreadyExistsError()
        if data.user_id is not None and await self._repository.get_by_user_id(data.user_id) is not None:
            raise TeacherAlreadyExistsError()

        teacher = Teacher(
            user_id=data.user_id,
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email,
            hire_date=data.hire_date,
        )
        try:
            return await self._repository.add(teacher)
        except IntegrityError as exc:
            # Pre-checks above narrow the window but don't close it — see
            # docs/adr/0004, same check-then-create race guard as every
            # other domain's create().
            raise TeacherAlreadyExistsError() from exc

    async def get(self, teacher_id: UUID) -> Teacher:
        teacher = await self._repository.get(teacher_id)
        if teacher is None:
            raise TeacherNotFoundError()
        return teacher

    async def list(self, *, limit: int, offset: int) -> tuple[list[Teacher], int]:
        return await self._repository.list(limit=limit, offset=offset)

    async def update(self, teacher_id: UUID, data: TeacherUpdate) -> Teacher:
        teacher = await self.get(teacher_id)
        updates = data.model_dump(exclude_unset=True)

        new_email = updates.get("email")
        if new_email is not None and new_email != teacher.email:
            existing = await self._repository.get_by_email(new_email)
            if existing is not None and existing.id != teacher_id:
                raise TeacherAlreadyExistsError()

        new_user_id = updates.get("user_id")
        if new_user_id is not None and new_user_id != teacher.user_id:
            existing = await self._repository.get_by_user_id(new_user_id)
            if existing is not None and existing.id != teacher_id:
                raise TeacherAlreadyExistsError()

        for field, value in updates.items():
            setattr(teacher, field, value)
        try:
            return await self._repository.add(teacher)
        except IntegrityError as exc:
            # Pre-checks above narrow the window but don't close it — see
            # docs/adr/0004, same check-then-create race guard as create().
            raise TeacherAlreadyExistsError() from exc

    async def delete(self, teacher_id: UUID) -> None:
        teacher = await self.get(teacher_id)
        if teacher.profile_picture_path is not None:
            Path(settings.upload_dir, teacher.profile_picture_path).unlink(missing_ok=True)
        await self._repository.remove(teacher)

    async def upload_profile_picture(self, teacher_id: UUID, file: UploadFile) -> Teacher:
        teacher = await self.get(teacher_id)
        path = await file_storage.save_profile_picture(
            file, subdir="teachers", entity_id=teacher.id
        )
        teacher.profile_picture_path = path
        return await self._repository.add(teacher)


class TeacherChangeRequestService:
    def __init__(
        self,
        repository: TeacherChangeRequestRepository,
        teacher_repository: TeacherRepository,
        teacher_service: TeacherService,
    ) -> None:
        self._repository = repository
        self._teacher_repository = teacher_repository
        self._teacher_service = teacher_service

    async def get_my_teacher(self, user_id: UUID) -> Teacher:
        teacher = await self._teacher_repository.get_by_user_id(user_id)
        if teacher is None:
            raise TeacherHasNoLinkedRecordError()
        return teacher

    async def create(
        self, user_id: UUID, data: TeacherChangeRequestCreate
    ) -> TeacherChangeRequest:
        teacher = await self.get_my_teacher(user_id)
        if await self._repository.get_pending_by_teacher_id(teacher.id) is not None:
            raise PendingChangeRequestExistsError()

        request = TeacherChangeRequest(
            teacher_id=teacher.id,
            requested_by=user_id,
            proposed_changes=data.model_dump(exclude_unset=True, exclude_none=True),
            status=ChangeRequestStatus.PENDING,
        )
        try:
            return await self._repository.add(request)
        except IntegrityError as exc:
            # The pre-check above narrows the window but doesn't close it —
            # the partial unique index on models.py is the real guard.
            raise PendingChangeRequestExistsError() from exc

    async def list_all(self, *, limit: int, offset: int) -> tuple[list[TeacherChangeRequest], int]:
        return await self._repository.list(limit=limit, offset=offset)

    async def _get_pending(self, request_id: UUID) -> TeacherChangeRequest:
        request = await self._repository.get(request_id)
        if request is None:
            raise TeacherChangeRequestNotFoundError()
        if request.status != ChangeRequestStatus.PENDING:
            raise ChangeRequestNotPendingError()
        return request

    async def approve(self, request_id: UUID, reviewer_id: UUID) -> TeacherChangeRequest:
        request = await self._get_pending(request_id)
        # Reuses TeacherService.update — same validation and
        # uniqueness-race handling as a direct admin PATCH, not duplicated
        # here. If this raises (e.g. the email was taken by someone else
        # between request and approval), it propagates before the request
        # is marked approved, so the request stays PENDING rather than
        # silently recording an approval that didn't actually apply.
        await self._teacher_service.update(
            request.teacher_id, TeacherUpdate(**request.proposed_changes)
        )
        request.status = ChangeRequestStatus.APPROVED
        request.reviewed_by = reviewer_id
        request.reviewed_at = datetime.now(timezone.utc)
        return await self._repository.add(request)

    async def reject(self, request_id: UUID, reviewer_id: UUID) -> TeacherChangeRequest:
        request = await self._get_pending(request_id)
        request.status = ChangeRequestStatus.REJECTED
        request.reviewed_by = reviewer_id
        request.reviewed_at = datetime.now(timezone.utc)
        return await self._repository.add(request)
