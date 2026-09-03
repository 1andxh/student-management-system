from uuid import UUID

from sqlalchemy.exc import IntegrityError

from sms.domains.academic_years.exceptions import AcademicYearNotFoundError, TermNotFoundError
from sms.domains.academic_years.repository import AcademicYearRepository, TermRepository
from sms.domains.classes.exceptions import ClassNotFoundError
from sms.domains.classes.models import Class
from sms.domains.classes.repository import ClassRepository
from sms.domains.enrollments.models import Enrollment, EnrollmentStatus
from sms.domains.enrollments.repository import EnrollmentRepository
from sms.domains.sections.exceptions import (
    ClassAlreadyAttachedError,
    ClassNotAttachedError,
    ClassYearMismatchError,
    GradeLevelAlreadyExistsError,
    GradeLevelNotFoundError,
    SectionAlreadyExistsError,
    SectionAssignmentNotFoundError,
    SectionFullError,
    SectionNotFoundError,
    StudentAlreadyAssignedError,
)
from sms.domains.sections.models import GradeLevel, Section, SectionAssignment
from sms.domains.sections.repository import (
    GradeLevelRepository,
    SectionAssignmentRepository,
    SectionRepository,
)
from sms.domains.sections.schemas import (
    GradeLevelCreate,
    GradeLevelUpdate,
    SectionCreate,
    SectionUpdate,
)
from sms.domains.students.exceptions import StudentNotFoundError
from sms.domains.students.repository import StudentRepository
from sms.domains.teachers.exceptions import TeacherNotFoundError
from sms.domains.teachers.repository import TeacherRepository


class GradeLevelService:
    def __init__(self, repository: GradeLevelRepository) -> None:
        self._repository = repository

    async def create(self, data: GradeLevelCreate) -> GradeLevel:
        if await self._repository.get_by_name(data.name) is not None:
            raise GradeLevelAlreadyExistsError()
        if await self._repository.get_by_rank(data.rank) is not None:
            raise GradeLevelAlreadyExistsError()

        grade_level = GradeLevel(name=data.name, rank=data.rank)
        try:
            return await self._repository.add(grade_level)
        except IntegrityError as exc:
            # Pre-checks narrow the window but don't close it — the unique
            # constraints are the real guard (docs/adr/0004).
            raise GradeLevelAlreadyExistsError() from exc

    async def get(self, grade_level_id: UUID) -> GradeLevel:
        grade_level = await self._repository.get(grade_level_id)
        if grade_level is None:
            raise GradeLevelNotFoundError()
        return grade_level

    async def list(self, *, limit: int, offset: int) -> tuple[list[GradeLevel], int]:
        return await self._repository.list(limit=limit, offset=offset)

    async def update(self, grade_level_id: UUID, data: GradeLevelUpdate) -> GradeLevel:
        grade_level = await self.get(grade_level_id)
        updates = data.model_dump(exclude_unset=True)

        new_name = updates.get("name")
        if new_name is not None and new_name != grade_level.name:
            existing = await self._repository.get_by_name(new_name)
            if existing is not None and existing.id != grade_level_id:
                raise GradeLevelAlreadyExistsError()

        new_rank = updates.get("rank")
        if new_rank is not None and new_rank != grade_level.rank:
            existing = await self._repository.get_by_rank(new_rank)
            if existing is not None and existing.id != grade_level_id:
                raise GradeLevelAlreadyExistsError()

        for field, value in updates.items():
            setattr(grade_level, field, value)
        try:
            return await self._repository.add(grade_level)
        except IntegrityError as exc:
            raise GradeLevelAlreadyExistsError() from exc

    async def delete(self, grade_level_id: UUID) -> None:
        grade_level = await self.get(grade_level_id)
        await self._repository.remove(grade_level)


class SectionService:
    """Owns attaching/detaching a Class to a Section — deliberately not
    ClassService, which would otherwise need to import the enrollments
    domain for the back-fill while enrollments already imports classes (a
    circular-import risk given both packages re-export their services).
    This keeps exactly one path that can set Class.section_id."""

    def __init__(
        self,
        repository: SectionRepository,
        grade_level_repository: GradeLevelRepository,
        academic_year_repository: AcademicYearRepository,
        teacher_repository: TeacherRepository,
        class_repository: ClassRepository,
        enrollment_repository: EnrollmentRepository,
        assignment_repository: SectionAssignmentRepository,
        term_repository: TermRepository,
    ) -> None:
        self._repository = repository
        self._grade_levels = grade_level_repository
        self._academic_years = academic_year_repository
        self._teachers = teacher_repository
        self._classes = class_repository
        self._enrollments = enrollment_repository
        self._assignments = assignment_repository
        self._terms = term_repository

    async def create(self, data: SectionCreate) -> Section:
        if await self._grade_levels.get(data.grade_level_id) is None:
            raise GradeLevelNotFoundError()
        if await self._academic_years.get(data.academic_year_id) is None:
            raise AcademicYearNotFoundError()
        if data.class_teacher_id is not None:
            if await self._teachers.get(data.class_teacher_id) is None:
                raise TeacherNotFoundError()

        if (
            await self._repository.get_by_name(
                data.grade_level_id, data.academic_year_id, data.name
            )
            is not None
        ):
            raise SectionAlreadyExistsError()

        section = Section(
            grade_level_id=data.grade_level_id,
            academic_year_id=data.academic_year_id,
            name=data.name,
            capacity=data.capacity,
            class_teacher_id=data.class_teacher_id,
        )
        try:
            return await self._repository.add(section)
        except IntegrityError as exc:
            raise SectionAlreadyExistsError() from exc

    async def get(self, section_id: UUID) -> Section:
        section = await self._repository.get(section_id)
        if section is None:
            raise SectionNotFoundError()
        return section

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        grade_level_id: UUID | None = None,
        academic_year_id: UUID | None = None,
    ) -> tuple[list[Section], int]:
        return await self._repository.list(
            limit=limit,
            offset=offset,
            grade_level_id=grade_level_id,
            academic_year_id=academic_year_id,
        )

    async def update(self, section_id: UUID, data: SectionUpdate) -> Section:
        section = await self.get(section_id)
        updates = data.model_dump(exclude_unset=True)

        if "class_teacher_id" in updates and updates["class_teacher_id"] is not None:
            if await self._teachers.get(updates["class_teacher_id"]) is None:
                raise TeacherNotFoundError()

        new_name = updates.get("name")
        if new_name is not None and new_name != section.name:
            existing = await self._repository.get_by_name(
                section.grade_level_id, section.academic_year_id, new_name
            )
            if existing is not None and existing.id != section_id:
                raise SectionAlreadyExistsError()

        for field, value in updates.items():
            setattr(section, field, value)
        try:
            return await self._repository.add(section)
        except IntegrityError as exc:
            raise SectionAlreadyExistsError() from exc

    async def delete(self, section_id: UUID) -> None:
        section = await self.get(section_id)
        await self._repository.remove(section)

    async def _get_class(self, class_id: UUID) -> Class:
        cls = await self._classes.get(class_id)
        if cls is None:
            raise ClassNotFoundError()
        return cls

    async def attach_class(self, section_id: UUID, class_id: UUID) -> Section:
        """Marks a Class as taught to this Section, then back-fills an
        Enrollment row for every student already assigned to the section.
        Idempotent — attaching twice creates no duplicate enrollments."""
        # Locking read, not a plain get — this method reads the roster and
        # writes enrollments derived from it, so it has to serialise against
        # a concurrent assign() on the same section. Without the lock the two
        # interleave cleanly and silently drop an enrollment: assign() reads
        # "no classes attached yet" while this reads "student not on the
        # roster yet", both commit, and the student ends up assigned to the
        # section but not enrolled in this class (security-auditor finding).
        section = await self._repository.get_for_update(section_id)
        if section is None:
            raise SectionNotFoundError()
        cls = await self._get_class(class_id)

        # Re-attaching a class that already belongs to another section would
        # silently orphan that section's enrollments AND stack both rosters
        # onto one class — unbounded overshoot of Class.capacity, the very
        # invariant EnrollmentService.enroll takes a row lock to protect
        # (docs/adr/0017). Make it an explicit detach-then-attach instead.
        if cls.section_id is not None and cls.section_id != section.id:
            raise ClassAlreadyAttachedError()

        # A Class has no academic year of its own — it's reached through
        # Class.term_id -> Term.academic_year_id. Without this check, attaching
        # a class from a different year auto-enrols the whole roster into it,
        # handing that class's teacher gradebook read/write over an unrelated
        # cohort from a single mistyped UUID (security-auditor finding).
        term = await self._terms.get(cls.term_id)
        if term is None:
            raise TermNotFoundError()
        if term.academic_year_id != section.academic_year_id:
            raise ClassYearMismatchError()

        cls.section_id = section.id
        try:
            await self._classes.add(cls, commit=False)
            assignments = await self._assignments.list_by_section_id(section.id)
            for assignment in assignments:
                existing = await self._enrollments.get_by_student_and_class(
                    assignment.student_id, cls.id
                )
                if existing is not None:
                    continue
                await self._enrollments.add(
                    Enrollment(
                        student_id=assignment.student_id,
                        class_id=cls.id,
                        status=EnrollmentStatus.ACTIVE,
                    ),
                    commit=False,
                )
            await self._repository.commit()
        except Exception:
            await self._repository.rollback()
            raise
        return section

    async def detach_class(self, section_id: UUID, class_id: UUID) -> Section:
        """Clears Class.section_id. Deliberately leaves existing Enrollment
        rows intact — they're real academic-record data, the same
        protective reasoning behind the RESTRICT FKs on Enrollment."""
        section = await self.get(section_id)
        cls = await self._get_class(class_id)

        # 409 rather than a silent 200 no-op — detaching a class that was
        # never attached to this section is a wrong-UUID call, and silently
        # succeeding hides it (security-auditor finding).
        if cls.section_id != section.id:
            raise ClassNotAttachedError()

        cls.section_id = None
        await self._classes.add(cls)
        return section


class SectionAssignmentService:
    def __init__(
        self,
        repository: SectionAssignmentRepository,
        section_repository: SectionRepository,
        student_repository: StudentRepository,
        class_repository: ClassRepository,
        enrollment_repository: EnrollmentRepository,
    ) -> None:
        self._repository = repository
        self._sections = section_repository
        self._students = student_repository
        self._classes = class_repository
        self._enrollments = enrollment_repository

    async def assign(self, student_id: UUID, section_id: UUID) -> SectionAssignment:
        if await self._students.get(student_id) is None:
            raise StudentNotFoundError()

        # Locks the Section row — held until this method's own commit
        # below, so two concurrent assignments can't both see room for the
        # last seat. Same pattern as Enrollment's capacity guard
        # (docs/adr/0017): nothing between here and the commit may commit
        # on this session, which is why every write below uses commit=False.
        section = await self._sections.get_for_update(section_id)
        if section is None:
            raise SectionNotFoundError()

        if (
            await self._repository.get_by_student_and_year(student_id, section.academic_year_id)
            is not None
        ):
            raise StudentAlreadyAssignedError()

        assigned_count = await self._repository.count_by_section_id(section.id)
        if assigned_count >= section.capacity:
            raise SectionFullError()

        assignment = SectionAssignment(
            student_id=student_id,
            section_id=section.id,
            # Derived from the section, never from caller input — this
            # column exists solely to make the one-section-per-year rule a
            # real DB constraint.
            academic_year_id=section.academic_year_id,
        )
        try:
            created = await self._repository.add(assignment, commit=False)

            # Auto-enroll into every class taught to this section. Per-class
            # capacity is deliberately NOT enforced here: for a
            # section-taught class the section's capacity is the governing
            # constraint, and failing a section assignment because one of
            # several attached classes has a smaller capacity would be a
            # confusing, unrelated failure.
            for cls in await self._classes.list_by_section_id(section.id):
                existing = await self._enrollments.get_by_student_and_class(student_id, cls.id)
                if existing is not None:
                    continue
                await self._enrollments.add(
                    Enrollment(
                        student_id=student_id,
                        class_id=cls.id,
                        status=EnrollmentStatus.ACTIVE,
                    ),
                    commit=False,
                )
            await self._repository.commit()
        except IntegrityError as exc:
            await self._repository.rollback()
            # Only translate the constraint this pre-check is actually
            # racing — uq_section_assignments_student_year. A different
            # IntegrityError here (an FK violation, or a duplicate from the
            # enrollment fan-out) is a genuinely different failure, and
            # reporting it as "already assigned to a section" would send
            # anyone debugging it down the wrong path entirely.
            constraint = getattr(exc.orig, "constraint_name", None)
            if constraint is not None and constraint != "uq_section_assignments_student_year":
                raise
            raise StudentAlreadyAssignedError() from exc
        except Exception:
            await self._repository.rollback()
            raise
        return created

    async def unassign(self, student_id: UUID, section_id: UUID) -> None:
        """Removes the section assignment. Deliberately leaves any
        auto-created Enrollment rows in place — dropping a class is an
        explicit action through the enrollments domain, not a side effect
        of moving between sections."""
        assignment = await self._repository.get_by_student_and_section(student_id, section_id)
        if assignment is None:
            raise SectionAssignmentNotFoundError()
        await self._repository.remove(assignment)

    async def list_roster(self, section_id: UUID) -> list[SectionAssignment]:
        section = await self._sections.get(section_id)
        if section is None:
            raise SectionNotFoundError()
        return await self._repository.list_by_section_id(section.id)
