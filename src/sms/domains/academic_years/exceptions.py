from sms.core.exceptions import ConflictError, NotFoundError


class AcademicYearNotFoundError(NotFoundError):
    message = "Academic year not found."


class AcademicYearAlreadyExistsError(ConflictError):
    message = "An academic year with this name already exists."


class TermNotFoundError(NotFoundError):
    message = "Term not found."


class TermAlreadyExistsError(ConflictError):
    message = "A term with this name already exists for this academic year."


class TermOutsideAcademicYearError(ConflictError):
    message = "Term dates must fall within the academic year's date range."
