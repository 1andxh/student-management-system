class AppException(Exception):
    """Base for all application-raised errors. Services raise these (or a
    domain subclass); routers never construct HTTPException by hand."""

    status_code: int = 500
    message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message
        super().__init__(self.message)


class NotFoundError(AppException):
    status_code = 404
    message = "Resource not found."


class ConflictError(AppException):
    status_code = 409
    message = "Resource already exists."


class UnauthorizedError(AppException):
    status_code = 401
    message = "Authentication required."


class PermissionDeniedError(AppException):
    status_code = 403
    message = "You do not have permission to perform this action."
