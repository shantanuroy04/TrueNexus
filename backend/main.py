"""TrueNexus API. Run from this folder: uvicorn main:app --port 8000"""
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.datastructures import MutableHeaders

from routers import auth, combined, email, meta, url
from services import db, runtime
from services.eml import MAX_EML_BYTES

MAX_BODY_BYTES = 256 * 1024
log = logging.getLogger("mlphil")


class Guard:
    """Body size cap, security headers and input-free request logging (R6)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = time.perf_counter()
        declared = dict(scope["headers"]).get(b"content-length", b"0")
        seen = int(declared) if declared.isdigit() else 0
        limit = MAX_EML_BYTES if scope["path"] == "/api/check-eml" else MAX_BODY_BYTES

        async def capped_receive():
            # Raised inside body parsing, so CORS and the headers below still apply.
            nonlocal seen
            if seen > limit:
                raise HTTPException(413, "Request is too large.")
            message = await receive()
            seen += len(message.get("body", b""))
            if seen > limit:
                raise HTTPException(413, "Request is too large.")
            return message

        async def secured_send(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Referrer-Policy"] = "no-referrer"
                if scope["method"] == "POST":
                    headers["Cache-Control"] = "no-store"
                elapsed_ms = (time.perf_counter() - started) * 1000
                log.info("status=%s latency_ms=%.0f", message["status"], elapsed_ms)
            await send(message)

        await self.app(scope, capped_receive, secured_send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.url_model, url_version = runtime.try_load("url", runtime.load_url_model)
    app.state.email_model, email_version = runtime.try_load("email", runtime.load_email_model)
    app.state.versions = {"url": url_version, "email": email_version}
    try:
        db.init()
        app.state.db_ready = True
    except Exception as exc:  # accounts go down; URL and email checks keep working
        log.warning("accounts database unavailable: %s", type(exc).__name__)
        app.state.db_ready = False
    yield


def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("uvicorn.access").disabled = True  # access lines include query strings
    app = FastAPI(title="TrueNexus API", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.limiter = runtime.limiter
    origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins if o.strip() and o.strip() != "*"],
        allow_methods=["GET", "POST"],
        allow_credentials=True,  # session cookie; safe only because origins are an explicit list
        allow_headers=["Content-Type"],  # also covers message/rfc822 uploads
    )
    app.add_middleware(Guard)  # added last, so outermost: covers CORS preflights too

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, __: RequestValidationError):
        # FastAPI's default 422 echoes the submitted input back.
        return JSONResponse({"detail": "Request is missing a field or has one that is too long."}, 422)

    @app.exception_handler(RateLimitExceeded)
    async def rate_limited(_: Request, __: RateLimitExceeded):
        return JSONResponse({"detail": "Too many checks. Wait a minute and try again."}, 429)

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception):
        log.error("unhandled: %s", type(exc).__name__)
        return JSONResponse({"detail": "UNAVAILABLE"}, 503)

    for module in (meta, url, email, combined, auth):
        app.include_router(module.router)
    return app


app = create_app()
