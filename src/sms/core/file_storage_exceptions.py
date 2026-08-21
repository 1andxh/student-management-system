from sms.core.exceptions import AppException


class InvalidFileTypeError(AppException):
    status_code = 415
    message = "Unsupported file type. Allowed: JPEG, PNG, WebP."


class FileTooLargeError(AppException):
    status_code = 413
    message = "File exceeds the maximum allowed size."
