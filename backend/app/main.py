from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes import (
    admin,
    auth,
    community,
    curriculum,
    health,
    imports,
    workflows,
)
from app.core.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app):
    if settings.environment == "development":
        from pathlib import Path

        from alembic import command
        from alembic.config import Config

        command.upgrade(
            Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head"
        )
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=auth.build_session_secret(),
    # The deployed frontend and API use different HTTPS origins (Vercel and
    # Render). Production cookies must therefore be allowed on cross-site API
    # requests; local development remains same-site friendly.
    same_site="none" if settings.environment == "production" else "lax",
    https_only=settings.environment == "production",
    max_age=28800,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(curriculum.router, prefix="/api")
app.include_router(workflows.router, prefix="/api")
app.include_router(imports.router, prefix="/api")
app.include_router(community.router, prefix="/api")


@app.exception_handler(IntegrityError)
async def conflicting_record(request: Request, exc: IntegrityError):
    return JSONResponse(
        {"detail": "This change conflicts with an existing record. Refresh and retry."},
        status_code=409,
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if origin != settings.frontend_origin:
            return JSONResponse(
                {"detail": "Request origin is not allowed."}, status_code=403
            )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    return response
