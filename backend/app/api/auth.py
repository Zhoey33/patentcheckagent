"""这个文件用于提供登录、登出和当前用户接口。"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.deps import get_current_user
from app.models.user import User
from app.schemas.auth import LoginRequest, UserRead
from app.services.errors import UserFacingError

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=UserRead)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """Authenticate an internal user and set an HttpOnly access token cookie."""

    user = db.scalar(select(User).where(User.username == payload.username))
    password_matches = user is not None and verify_password(payload.password, user.password_hash)
    if user is None or not user.is_active or not password_matches:
        raise UserFacingError("账号或密码错误。", status_code=401)

    token = create_access_token(user.id, settings)
    secure_cookie = settings.app_env == "production"
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        max_age=settings.access_token_expire_minutes * 60,
    )
    return user


@router.post("/logout")
def logout(response: Response) -> dict[str, bool]:
    """Clear the authentication cookie."""

    response.delete_cookie("access_token")
    return {"ok": True}


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> User:
    """Return the current authenticated user."""

    return current_user
