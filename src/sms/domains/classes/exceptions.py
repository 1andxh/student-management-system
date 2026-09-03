from sms.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError


class SubjectNotFoundError(NotFoundError):
    message = "Subject not found."


class SubjectAlreadyExistsError(ConflictError):
    message = "A subject with this code already exists."


class ClassNotFoundError(NotFoundError):
    message = "Class not found."


class NotYourClassError(PermissionDeniedError):
    message = "You do not teach this class."


class ClassAttachedToSectionError(ConflictError):
    message = (
        "This class is attached to a section and is pinned to that section's "
        "academic year. Detach it from the section before changing its term."
    )


# Deliberately no ClassAlreadyExistsError — Class has no uniqueness
# constraint (a teacher can run two sections of the same subject in one
# term; see docs/adr/0016).
