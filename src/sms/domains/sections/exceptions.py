from sms.core.exceptions import ConflictError, NotFoundError


class GradeLevelNotFoundError(NotFoundError):
    message = "Grade level not found."


class GradeLevelAlreadyExistsError(ConflictError):
    message = "A grade level with this name or rank already exists."


class SectionNotFoundError(NotFoundError):
    message = "Section not found."


class SectionAlreadyExistsError(ConflictError):
    message = "A section with this name already exists for this grade level and academic year."


class SectionFullError(ConflictError):
    message = "This section has no available capacity."


class SectionAssignmentNotFoundError(NotFoundError):
    message = "This student is not assigned to this section."


class StudentAlreadyAssignedError(ConflictError):
    message = "This student is already assigned to a section for this academic year."


class ClassAlreadyAttachedError(ConflictError):
    message = "This class is already attached to a different section. Detach it first."


class ClassNotAttachedError(ConflictError):
    message = "This class is not attached to this section."


class ClassYearMismatchError(ConflictError):
    message = "This class belongs to a different academic year than this section."
