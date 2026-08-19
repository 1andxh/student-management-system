from fastapi import FastAPI
from slowapi.middleware import SlowAPIMiddleware

from sms.api.router import api_router
from sms.core.exception_handlers import register_exception_handlers
from sms.core.logging import configure_logging
from sms.core.middleware import RequestLoggingMiddleware
from sms.core.rate_limit import limiter


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(title="School Management System")
    app.state.limiter = limiter

    register_exception_handlers(app)
    # SlowAPIMiddleware added first (so RequestLoggingMiddleware, added
    # last, ends up outermost) — a rate-limited request still gets a real
    # structlog line, not skipped.
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.include_router(api_router)

    return app


app = create_app()
