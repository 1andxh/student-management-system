from sms.core.exceptions import ConflictError, NotFoundError


class StudentNotFoundError(NotFoundError):
    message = "Student not found."


class StudentAlreadyExistsError(ConflictError):
    message = "A student with this email or student number already exists."
