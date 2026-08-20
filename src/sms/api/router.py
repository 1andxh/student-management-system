from fastapi import APIRouter

from sms.domains.academic_years.router import academic_years_router, terms_router
from sms.domains.assessments.router import assessments_router, grades_router
from sms.domains.audit.router import router as audit_router
from sms.domains.auth.router import router as auth_router
from sms.domains.classes.router import classes_router, subjects_router
from sms.domains.enrollments.router import router as enrollments_router
from sms.domains.students.router import router as students_router
from sms.domains.teachers.router import router as teachers_router
from sms.domains.users.router import router as users_router

api_router = APIRouter()


@api_router.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


# Domain routers are added here as they're built, one line each — main.py
# only ever imports this module, so it never grows with the domain count.
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(audit_router)
api_router.include_router(students_router)
api_router.include_router(teachers_router)
api_router.include_router(academic_years_router)
api_router.include_router(terms_router)
api_router.include_router(subjects_router)
api_router.include_router(classes_router)
api_router.include_router(enrollments_router)
api_router.include_router(assessments_router)
api_router.include_router(grades_router)
