"""这个文件用于提供管理员账号维护和全量审查任务查询接口。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.security import hash_password
from app.db.session import get_db
from app.deps import get_current_admin
from app.models.patent_check_task import PatentCheckTask
from app.models.user import User
from app.schemas.admin import (
    AdminPasswordReset,
    AdminTaskList,
    AdminUserCreate,
    AdminUserList,
    AdminUserUpdate,
)
from app.schemas.auth import UserRead
from app.services.errors import UserFacingError

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=AdminUserList)
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> AdminUserList:
    """List all internal accounts for administrators."""

    items = db.scalars(select(User).order_by(User.created_at.desc())).all()
    return AdminUserList(items=list(items), total=len(items))


@router.post("/users", response_model=UserRead)
def create_user(
    payload: AdminUserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> User:
    """Create a new internal account."""

    existing = db.scalar(select(User).where(User.username == payload.username))
    if existing is not None:
        raise UserFacingError("账号已存在。")

    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=payload.is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: str,
    payload: AdminUserUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> User:
    """Update role or active status for an internal account."""

    user = db.get(User, user_id)
    if user is None:
        raise UserFacingError("账号不存在。", status_code=404)
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    return user


@router.post("/users/{user_id}/reset-password", response_model=UserRead)
def reset_password(
    user_id: str,
    payload: AdminPasswordReset,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> User:
    """Reset password for an internal account."""

    user = db.get(User, user_id)
    if user is None:
        raise UserFacingError("账号不存在。", status_code=404)
    user.password_hash = hash_password(payload.password)
    db.commit()
    db.refresh(user)
    return user


@router.get("/patent-checks", response_model=AdminTaskList)
def list_all_patent_checks(
    status: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> AdminTaskList:
    """List all patent check tasks for administrators."""

    stmt = select(PatentCheckTask).options(selectinload(PatentCheckTask.files))
    count_stmt = select(func.count(PatentCheckTask.id))
    if status:
        stmt = stmt.where(PatentCheckTask.status == status)
        count_stmt = count_stmt.where(PatentCheckTask.status == status)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(PatentCheckTask.title.ilike(like))
        count_stmt = count_stmt.where(PatentCheckTask.title.ilike(like))

    total = db.scalar(count_stmt) or 0
    items = db.scalars(
        stmt.order_by(PatentCheckTask.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return AdminTaskList(items=list(items), total=total, page=page, page_size=page_size)
