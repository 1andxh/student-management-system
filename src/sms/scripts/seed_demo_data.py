"""Populates an empty database with a small, coherent school so the API has
something to serve. Intended for local development and for the companion
frontend to build against.

    docker compose exec api uv run python -m sms.scripts.seed_demo_data

Everything is created **through the domain services**, not by inserting rows
directly. That is deliberate and costs a little verbosity: it means the seed
respects every business rule the API enforces (uniqueness races, section
capacity, timetable conflict detection, auto-enrollment on section
assignment), so a seed that runs clean is also evidence the domains compose
correctly. A raw-SQL fixture would happily produce a school the API itself
would have rejected.

Refuses to run against a database that already has demo data rather than
attempting a partial top-up — a half-seeded school with ambiguous state is
worse than none. Reset with:

    docker compose exec api uv run alembic downgrade base
    docker compose exec api uv run alembic upgrade head

The generated teacher passwords and student PINs are shown **once**, here,
at the end — the API never returns them again (docs/adr/0021, 0024). Copy
them somewhere before closing the terminal.
"""

import asyncio
import sys
from datetime import date, time

from sms.db.session import async_session_factory
from sms.domains.academic_years.repository import AcademicYearRepository, TermRepository
from sms.domains.academic_years.schemas import AcademicYearCreate, TermCreate
from sms.domains.academic_years.service import AcademicYearService, TermService
from sms.domains.assessments.repository import AssessmentRepository, GradeRepository
from sms.domains.assessments.schemas import AssessmentCreate, GradeCreate
from sms.domains.assessments.service import AssessmentService, GradeService
from sms.domains.audit.repository import AuditLogRepository
from sms.domains.audit.service import AuditService
from sms.domains.classes.repository import ClassRepository, SubjectRepository
from sms.domains.classes.schemas import ClassCreate, SubjectCreate
from sms.domains.classes.service import ClassService, SubjectService
from sms.domains.enrollments.repository import EnrollmentRepository
from sms.domains.sections.repository import (
    GradeLevelRepository,
    SectionAssignmentRepository,
    SectionRepository,
)
from sms.domains.sections.schemas import GradeLevelCreate, SectionCreate
from sms.domains.sections.service import (
    GradeLevelService,
    SectionAssignmentService,
    SectionService,
)
from sms.domains.students.repository import StudentRepository
from sms.domains.students.schemas import StudentCreate
from sms.domains.students.service import StudentService
from sms.domains.teachers.repository import TeacherRepository
from sms.domains.teachers.schemas import TeacherCreate
from sms.domains.teachers.service import TeacherService
from sms.domains.timetable.models import DayOfWeek
from sms.domains.timetable.repository import PeriodRepository, ScheduleSlotRepository
from sms.domains.timetable.schemas import PeriodCreate, ScheduleSlotCreate
from sms.domains.timetable.service import PeriodService, ScheduleSlotService
from sms.domains.users.models import UserRole
from sms.domains.users.repository import UserRepository
from sms.domains.users.schemas import UserCreate
from sms.domains.users.service import UserService

ADMIN_EMAIL = "admin@demo.school"
ADMIN_PASSWORD = "demo-admin-password"

SUBJECTS = [
    ("Mathematics", "MATH"),
    ("English", "ENG"),
    ("Science", "SCI"),
    ("History", "HIST"),
]

# One teacher per subject, so "who teaches what" is unambiguous.
TEACHERS = [
    ("Ada", "Lovelace", "ada.lovelace@demo.school"),
    ("George", "Orwell", "george.orwell@demo.school"),
    ("Marie", "Curie", "marie.curie@demo.school"),
    ("Howard", "Zinn", "howard.zinn@demo.school"),
]

PERIODS = [
    ("Period 1", time(8, 0), time(8, 45)),
    ("Period 2", time(8, 50), time(9, 35)),
    ("Period 3", time(9, 50), time(10, 35)),
    ("Period 4", time(10, 40), time(11, 25)),
]

STUDENT_NAMES = [
    ("Grace", "Hopper"),
    ("Alan", "Turing"),
    ("Katherine", "Johnson"),
    ("Linus", "Torvalds"),
    ("Barbara", "Liskov"),
    ("Edsger", "Dijkstra"),
]


async def main() -> None:
    async with async_session_factory() as session:
        grade_levels = GradeLevelService(GradeLevelRepository(session))
        existing, _ = await grade_levels.list(limit=1, offset=0)
        if existing:
            print(
                "This database already has grade levels — refusing to seed on top of\n"
                "existing data. Reset first:\n"
                "  docker compose exec api uv run alembic downgrade base\n"
                "  docker compose exec api uv run alembic upgrade head",
                file=sys.stderr,
            )
            sys.exit(1)

        users = UserService(UserRepository(session), AuditService(AuditLogRepository(session)))
        years = AcademicYearService(AcademicYearRepository(session))
        terms = TermService(TermRepository(session), AcademicYearRepository(session))
        subjects = SubjectService(SubjectRepository(session))
        teachers = TeacherService(
            TeacherRepository(session), UserRepository(session), ClassRepository(session)
        )
        students = StudentService(StudentRepository(session), UserRepository(session))
        classes = ClassService(
            ClassRepository(session),
            SubjectRepository(session),
            TermRepository(session),
            TeacherRepository(session),
        )
        sections = SectionService(
            SectionRepository(session),
            GradeLevelRepository(session),
            AcademicYearRepository(session),
            TeacherRepository(session),
            ClassRepository(session),
            EnrollmentRepository(session),
            SectionAssignmentRepository(session),
            TermRepository(session),
        )
        assignments = SectionAssignmentService(
            SectionAssignmentRepository(session),
            SectionRepository(session),
            StudentRepository(session),
            ClassRepository(session),
            EnrollmentRepository(session),
        )
        periods = PeriodService(PeriodRepository(session))
        slots = ScheduleSlotService(
            ScheduleSlotRepository(session),
            PeriodRepository(session),
            ClassRepository(session),
            TeacherRepository(session),
            StudentRepository(session),
            SectionAssignmentRepository(session),
        )
        assessments = AssessmentService(
            AssessmentRepository(session), ClassRepository(session), TeacherRepository(session)
        )
        grades = GradeService(
            GradeRepository(session),
            AssessmentRepository(session),
            StudentRepository(session),
            EnrollmentRepository(session),
            ClassRepository(session),
            TeacherRepository(session),
        )

        # An ADMIN, not a SUPER_ADMIN — this is the account the frontend
        # logs in as, and it should have exactly the authority a real
        # day-to-day admin has. create_admin.py makes the SUPER_ADMIN.
        admin = await users.create(
            UserCreate(email=ADMIN_EMAIL, password=ADMIN_PASSWORD, role=UserRole.ADMIN),
            acting_user=None,
        )

        year = await years.create(
            AcademicYearCreate(
                name="2025-2026", start_date=date(2025, 9, 1), end_date=date(2026, 6, 30)
            )
        )
        term = await terms.create(
            TermCreate(
                academic_year_id=year.id,
                name="Autumn",
                start_date=date(2025, 9, 1),
                end_date=date(2025, 12, 19),
            )
        )

        created_subjects = [
            await subjects.create(SubjectCreate(name=name, code=code)) for name, code in SUBJECTS
        ]

        teacher_credentials: list[tuple[str, str]] = []
        created_teachers = []
        for first, last, email in TEACHERS:
            teacher = await teachers.create(
                TeacherCreate(
                    first_name=first, last_name=last, email=email, hire_date=date(2020, 9, 1)
                )
            )
            created_teachers.append(teacher)
            issued = await teachers.generate_credentials(teacher.id)
            teacher_credentials.append((issued.email, issued.password))

        created_periods = [
            await periods.create(PeriodCreate(name=name, start_time=start, end_time=end))
            for name, start, end in PERIODS
        ]

        # Two grade levels, one section each. Each section gets its own room
        # so the room-conflict rule never fires spuriously.
        section_specs = [("Grade 7", 7, "A", "Room 7A"), ("Grade 8", 8, "B", "Room 8B")]
        created_sections = []
        for level_name, rank, section_name, room in section_specs:
            level = await grade_levels.create(GradeLevelCreate(name=level_name, rank=rank))
            section = await sections.create(
                SectionCreate(
                    grade_level_id=level.id,
                    academic_year_id=year.id,
                    name=section_name,
                    capacity=30,
                )
            )
            created_sections.append((section, room))

        # Every section takes every subject. The subject order is rotated
        # per section so that no teacher is ever in two places at once —
        # a Latin square, which is what keeps the timetable's
        # teacher-double-booking rule satisfied. Getting this wrong is how
        # you find out the conflict detection works.
        section_classes: list[list] = []
        for section_index, (section, room) in enumerate(created_sections):
            row = []
            for period_index, period in enumerate(created_periods):
                subject_index = (period_index + section_index) % len(created_subjects)
                klass = await classes.create(
                    ClassCreate(
                        subject_id=created_subjects[subject_index].id,
                        term_id=term.id,
                        teacher_id=created_teachers[subject_index].id,
                        capacity=30,
                        room=room,
                    )
                )
                # Attaching before assigning students means the later
                # assignment auto-enrolls each student into all four
                # classes in one step (docs/adr/0024).
                await sections.attach_class(section.id, klass.id)
                await slots.create(
                    ScheduleSlotCreate(
                        class_id=klass.id,
                        day_of_week=DayOfWeek.MONDAY,
                        period_id=period.id,
                    )
                )
                row.append(klass)
            section_classes.append(row)

        # Students split evenly between the two sections. Assignment
        # auto-enrolls them into that section's classes.
        student_credentials: list[tuple[str, str]] = []
        section_students: list[list] = [[] for _ in created_sections]
        for index, (first, last) in enumerate(STUDENT_NAMES):
            section_index = index % len(created_sections)
            student = await students.create(
                StudentCreate(
                    first_name=first,
                    last_name=last,
                    date_of_birth=date(2013, 5, 14),
                    email=f"{first.lower()}.{last.lower()}@demo.school",
                    guardian_name=f"Guardian of {first}",
                    guardian_phone="+1-555-0100",
                )
            )
            issued = await students.generate_pin(student.id)
            student_credentials.append((issued.student_number, issued.pin))
            await assignments.assign(student.id, created_sections[section_index][0].id)
            section_students[section_index].append(student)

        # One graded assessment per section's first class, so the gradebook
        # endpoint has something to assemble.
        for section_index, row in enumerate(section_classes):
            klass = row[0]
            assessment = await assessments.create(
                admin,
                AssessmentCreate(
                    class_id=klass.id,
                    name="Autumn Quiz 1",
                    type="quiz",
                    max_score=20,
                    date=date(2025, 10, 3),
                ),
            )
            # Deliberately leaves the last student ungraded, so the
            # gradebook has a null cell to render.
            for offset, student in enumerate(section_students[section_index][:-1]):
                await grades.create(
                    admin,
                    GradeCreate(
                        assessment_id=assessment.id,
                        student_id=student.id,
                        score=12 + offset * 3,
                    ),
                )

    print("Seeded a demo school.\n")
    print("Admin login (email + password):")
    print(f"  {ADMIN_EMAIL}  /  {ADMIN_PASSWORD}\n")
    print("Teacher logins (email + password) — shown once, not recoverable:")
    for email, password in teacher_credentials:
        print(f"  {email}  /  {password}")
    print("\nStudent logins (student_number + PIN) — shown once, not recoverable:")
    for student_number, pin in student_credentials:
        print(f"  {student_number}  /  {pin}")
    print(
        "\nStudents log in at POST /auth/login-pin; admin and teachers at POST /auth/login."
    )


if __name__ == "__main__":
    asyncio.run(main())
