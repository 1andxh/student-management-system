from sms.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError


class UserNotFoundError(NotFoundError):
    message = "User not found."


class UserAlreadyExistsError(ConflictError):
    message = "A user with this email already exists."


class AdminTierProtectedError(PermissionDeniedError):
    message = "Only a super admin can create or modify an admin-tier account."


class LastSuperAdminError(ConflictError):
    message = "This action would leave no active super admin."
