"""这个文件用于定义 FastAPI 路由共享的依赖项。"""

import jwt
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.services.errors import UserFacingError


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """Resolve the current authenticated user from the HttpOnly cookie."""

    token = request.cookies.get("access_token")
    if not token:
        raise UserFacingError("请先登录。", status_code=401)
    try:
        user_id = decode_access_token(token, settings)
    except jwt.PyJWTError as exc:
        raise UserFacingError("登录状态已失效，请重新登录。", status_code=401) from exc

    user = db.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        raise UserFacingError("登录状态已失效，请重新登录。", status_code=401)
    return user


def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require the current user to be an active administrator."""

    if current_user.role != "admin":
        raise UserFacingError("无权访问管理员接口。", status_code=403)
    return current_user
