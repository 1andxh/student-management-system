from fastapi import APIRouter

from sms.domains.auth.router import router as auth_router
from sms.domains.students.router import router as students_router

api_router = APIRouter()


@api_router.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


# Domain routers are added here as they're built, one line each — main.py
# only ever imports this module, so it never grows with the domain count.
api_router.include_router(auth_router)
api_router.include_router(students_router)
