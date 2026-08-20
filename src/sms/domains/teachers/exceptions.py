from sms.core.exceptions import ConflictError, NotFoundError


class TeacherNotFoundError(NotFoundError):
    message = "Teacher not found."


class TeacherAlreadyExistsError(ConflictError):
    message = "A teacher with this email or user account already exists."


class TeacherChangeRequestNotFoundError(NotFoundError):
    message = "Change request not found."


class TeacherHasNoLinkedRecordError(NotFoundError):
    message = "No teacher record is linked to your account."


class PendingChangeRequestExistsError(ConflictError):
    message = "You already have a pending change request."


class ChangeRequestNotPendingError(ConflictError):
    message = "This change request has already been reviewed."
