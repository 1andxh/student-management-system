from fastapi import FastAPI

from sms.api.router import api_router
from sms.core.exception_handlers import register_exception_handlers
from sms.core.logging import configure_logging
from sms.core.middleware import RequestLoggingMiddleware


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(title="School Management System")

    app.add_middleware(RequestLoggingMiddleware)
    register_exception_handlers(app)
    app.include_router(api_router)

    return app


app = create_app()
