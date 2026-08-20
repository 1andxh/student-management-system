from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
    # CORS added last (outermost) so it can answer an OPTIONS preflight
    # before the request ever reaches rate-limiting/logging, and so CORS
    # headers land on every response, including ones from exception
    # handlers deeper in the stack. Origin is the sms-fronted Vite dev
    # server (127.0.0.1, not localhost — see that project's README for
    # why); expose_headers is required for the frontend's paginated list
    # views to read X-Total-Count at all, since browsers hide non-safelisted
    # response headers from JS by default even on a successful request.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Total-Count"],
    )
    app.include_router(api_router)

    return app


app = create_app()
