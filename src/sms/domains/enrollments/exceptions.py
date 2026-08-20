from sms.core.exceptions import ConflictError, NotFoundError


class EnrollmentNotFoundError(NotFoundError):
    message = "Enrollment not found."


class EnrollmentAlreadyExistsError(ConflictError):
    message = "This student is already enrolled in this class."


class ClassFullError(ConflictError):
    message = "This class has no available capacity."


class EnrollmentNotActiveError(ConflictError):
    message = "This enrollment is not active."
