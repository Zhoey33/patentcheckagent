"""这个文件用于提供专利审查任务创建、查询、报告和重试接口。"""

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.deps import get_current_user
from app.models.patent_check_task import PatentCheckTask
from app.models.user import User
from app.schemas.patent_check import PatentCheckReportRead, PatentCheckTaskList, PatentCheckTaskRead
from app.services.patent_check_service import (
    create_patent_check_task,
    enqueue_patent_check,
    get_task_for_user,
    list_tasks_for_user,
)

router = APIRouter(prefix="/api/patent-checks", tags=["patent-checks"])


@router.post("", response_model=PatentCheckTaskRead)
def create_task(
    title: str | None = Form(default=None),
    technical_field: str | None = Form(default=None),
    claims: UploadFile = File(...),
    specification: UploadFile = File(...),
    drawings: UploadFile = File(...),
    abstract: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    current_user: User = Depends(get_current_user),
) -> PatentCheckTask:
    """Create an asynchronous patent check task from uploaded PDF files."""

    return create_patent_check_task(
        db=db,
        settings=settings,
        user=current_user,
        title=title,
        technical_field=technical_field,
        uploads={
            "claims": claims,
            "specification": specification,
            "drawings": drawings,
            "abstract": abstract,
        },
    )


@router.get("", response_model=PatentCheckTaskList)
def list_tasks(
    status: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PatentCheckTaskList:
    """List patent check tasks visible to the current user."""

    items, total = list_tasks_for_user(db, current_user, status, keyword, page, page_size)
    return PatentCheckTaskList(items=items, total=total, page=page, page_size=page_size)


@router.get("/{task_id}", response_model=PatentCheckTaskRead)
def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PatentCheckTask:
    """Return one patent check task if the current user may access it."""

    return get_task_for_user(db, task_id, current_user)


@router.get("/{task_id}/report", response_model=PatentCheckReportRead)
def get_report(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PatentCheckReportRead:
    """Return the final Markdown report for a task."""

    task = get_task_for_user(db, task_id, current_user)
    return PatentCheckReportRead(
        id=task.id,
        status=task.status,
        final_report=task.final_report,
        error_message=task.error_message,
    )


@router.post("/{task_id}/retry", response_model=PatentCheckTaskRead)
def retry_task(
    task_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    current_user: User = Depends(get_current_user),
) -> PatentCheckTask:
    """Retry a failed task by moving it back to pending and enqueueing it."""

    task = get_task_for_user(db, task_id, current_user)
    if task.status != "failed":
        return task
    task.status = "pending"
    task.error_message = None
    db.commit()
    db.refresh(task)
    enqueue_patent_check(task.id, settings)
    return task
