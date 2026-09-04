from sms.core.exceptions import AppException, ConflictError, NotFoundError


class PeriodNotFoundError(NotFoundError):
    message = "Period not found."


class PeriodAlreadyExistsError(ConflictError):
    message = "A period with this name already exists."


class InvalidPeriodTimesError(AppException):
    # 422, subclassing AppException directly — core/exceptions.py has no
    # validation base, the same situation core/file_storage_exceptions.py
    # handled this way for 415/413. Exists because a partial PATCH can only
    # be validated against the stored row, so the schema can't catch it and
    # the service was previously raising a bare ValueError — which the
    # catch-all handler turned into a 500 plus a traceback for what is an
    # ordinary user typo (security-auditor finding).
    status_code = 422
    message = "end_time must be after start_time."


class PeriodInUseError(ConflictError):
    message = "This period is still used by one or more scheduled classes."


class PeriodOverlapsError(ConflictError):
    # Without this, the whole conflict-detection feature is bypassable:
    # every rule keys on period_id, so two periods covering the same clock
    # time let the same teacher, room and section be booked twice over
    # (security-auditor finding). Enforced by an EXCLUDE constraint rather
    # than a service check, which would race itself.
    message = "This period's times overlap an existing period."


class TimetableFilterRequiredError(AppException):
    status_code = 422
    message = "Specify at least one of class_id, teacher_id or section_id."


class ScheduleSlotNotFoundError(NotFoundError):
    message = "Schedule slot not found."


class SlotAlreadyScheduledError(ConflictError):
    message = "This class is already scheduled for this day and period."


# Three distinct errors rather than one generic "conflict" so the caller
# learns *which* rule fired — "the teacher is busy" and "the room is taken"
# need different fixes from whoever is building the timetable.
class TeacherDoubleBookedError(ConflictError):
    message = "This class's teacher already teaches another class in this day and period."


class RoomDoubleBookedError(ConflictError):
    message = "This class's room is already occupied in this day and period."


class SectionDoubleBookedError(ConflictError):
    message = "This class's section already has another class in this day and period."
