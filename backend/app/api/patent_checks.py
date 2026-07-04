"""这个文件用于提供专利审查任务创建、查询、事件流、报告和重试接口。"""

import asyncio
import json

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.deps import get_current_user
from app.models.patent_check_event import PatentCheckEvent
from app.models.patent_check_task import PatentCheckTask
from app.models.user import User
from app.schemas.patent_check import (
    PatentCheckEventList,
    PatentCheckReportRead,
    PatentCheckTaskList,
    PatentCheckTaskRead,
)
from app.services.errors import UserFacingError
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
    drawings: UploadFile | None = File(default=None),
    abstract: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    current_user: User = Depends(get_current_user),
) -> PatentCheckTask:
    """Create an asynchronous patent check task from uploaded PDF or Word files."""

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
        progress_stage=task.progress_stage,
        progress_percent=task.progress_percent,
        progress_message=task.progress_message,
        progress_steps=task.progress_steps,
        final_report=task.final_report,
        error_message=task.error_message,
    )


@router.get("/{task_id}/events", response_model=PatentCheckEventList)
def get_task_events(
    task_id: str,
    after_id: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PatentCheckEventList:
    """Return persisted Codex execution events for a task."""

    get_task_for_user(db, task_id, current_user)
    events = db.scalars(
        select(PatentCheckEvent)
        .where(PatentCheckEvent.task_id == task_id, PatentCheckEvent.id > after_id)
        .order_by(PatentCheckEvent.id)
    ).all()
    return PatentCheckEventList(items=list(events))


@router.get("/{task_id}/events/stream")
async def stream_task_events(
    task_id: str,
    request: Request,
    after_id: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Stream Codex execution events with Server-Sent Events."""

    get_task_for_user(db, task_id, current_user)
    current_user_id = current_user.id
    current_user_role = current_user.role

    async def event_generator():
        last_id = after_id
        terminal_statuses = {"succeeded", "failed", "cancelled"}
        while True:
            if await request.is_disconnected():
                break
            db.expire_all()
            task = get_task_for_user_scope(db, task_id, current_user_id, current_user_role)
            events = db.scalars(
                select(PatentCheckEvent)
                .where(PatentCheckEvent.task_id == task_id, PatentCheckEvent.id > last_id)
                .order_by(PatentCheckEvent.id)
                .limit(50)
            ).all()
            status_payload = {
                "status": task.status,
                "progress_stage": task.progress_stage,
                "progress_percent": task.progress_percent,
                "progress_message": task.progress_message,
            }
            for event in events:
                last_id = event.id
                yield format_sse(
                    "report_snapshot" if event.event_type == "report_snapshot" else "codex_event",
                    serialize_event(event),
                    event_id=event.id,
                )
            if status_payload["status"] in terminal_statuses:
                yield format_sse("task_status", status_payload)
                break
            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


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
    if not task.process_text_path:
        raise UserFacingError("任务输入已按安全策略清理，请重新提交文件后发起审查。")
    task.status = "pending"
    task.progress_stage = "queued"
    task.progress_percent = 5
    task.progress_message = "任务已重新提交，等待审查队列调度。"
    task.error_message = None
    task.stage_one_result = None
    task.final_report = None
    task.started_at = None
    task.finished_at = None
    task.input_cleanup_status = "pending"
    db.execute(delete(PatentCheckEvent).where(PatentCheckEvent.task_id == task.id))
    db.commit()
    db.refresh(task)
    enqueue_patent_check(task.id, settings)
    return task


def format_sse(event: str, payload: dict, event_id: int | None = None) -> str:
    """Serialize a Server-Sent Events frame."""

    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(payload, ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"


def serialize_event(event: PatentCheckEvent) -> dict:
    """Serialize one persisted patent check event for JSON and SSE responses."""

    return {
        "id": event.id,
        "task_id": event.task_id,
        "stage": event.stage,
        "event_type": event.event_type,
        "message": event.message,
        "content": event.content,
        "created_at": event.created_at.isoformat(),
    }


def get_task_for_user_scope(
    db: Session,
    task_id: str,
    user_id: str,
    user_role: str,
) -> PatentCheckTask:
    """Return a task for a scalar user scope inside a streaming response."""

    stmt = select(PatentCheckTask).where(PatentCheckTask.id == task_id)
    if user_role != "admin":
        stmt = stmt.where(PatentCheckTask.user_id == user_id)
    task = db.scalar(stmt)
    if task is None:
        raise UserFacingError("审查任务不存在或无权访问。", status_code=404)
    return task
