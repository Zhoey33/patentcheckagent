"""这个文件用于创建 FastAPI 应用、注册路由和统一错误处理。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import models  # noqa: F401
from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.patent_checks import router as patent_checks_router
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.services.errors import UserFacingError

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    """Create database tables when the application process starts."""

    Base.metadata.create_all(bind=engine)
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(title="专利文件智能审查系统 API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url, "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(UserFacingError)
    def handle_user_facing_error(_: Request, exc: UserFacingError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router)
    app.include_router(patent_checks_router)
    app.include_router(admin_router)
    return app


app = create_app()
