from sms.core.exceptions import ConflictError, NotFoundError


class AssessmentNotFoundError(NotFoundError):
    message = "Assessment not found."


class GradeNotFoundError(NotFoundError):
    message = "Grade not found."


class GradeAlreadyExistsError(ConflictError):
    message = "This student already has a grade for this assessment."


class ScoreExceedsMaxScoreError(ConflictError):
    message = "Score cannot exceed the assessment's max score."


class StudentNotEnrolledError(ConflictError):
    message = "This student is not actively enrolled in this assessment's class."
