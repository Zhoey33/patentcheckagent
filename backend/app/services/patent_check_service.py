"""这个文件用于编排专利审查任务创建、权限校验和队列投递。"""

import json
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from redis import Redis
from rq import Queue
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.models.patent_check_file import PatentCheckFile
from app.models.patent_check_task import PatentCheckTask
from app.models.user import User
from app.services.errors import UserFacingError
from app.services.pdf_extractor import extract_pdf_text

FILE_ROLES = {
    "claims": "权利要求书文件",
    "specification": "说明书文件",
    "drawings": "附图说明文件",
    "abstract": "摘要文件",
}


def ensure_pdf_upload(file: UploadFile, settings: Settings) -> bytes:
    """Validate an uploaded file and return its content bytes."""

    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise UserFacingError(f"{filename or '上传文件'} 格式不支持，第一版仅支持 PDF。")

    content = file.file.read()
    if len(content) > settings.max_file_size_bytes:
        raise UserFacingError(f"{filename} 超过 {settings.max_file_size_mb} MB 大小限制。")
    if not content:
        raise UserFacingError(f"{filename} 为空文件。")
    return content


def save_upload(content: bytes, filename: str, role: str, settings: Settings) -> Path:
    """Persist an uploaded PDF into the temporary upload directory."""

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    safe_suffix = Path(filename).suffix.lower() or ".pdf"
    path = settings.upload_dir / f"{role}-{uuid4()}{safe_suffix}"
    path.write_bytes(content)
    return path


def enqueue_patent_check(task_id: str, settings: Settings) -> None:
    """Enqueue a patent check task for the worker process."""

    if not settings.enable_worker_queue:
        return
    queue = Queue("patent-checks", connection=Redis.from_url(settings.redis_url))
    queue.enqueue("app.worker.run_patent_check_task", task_id, job_timeout=600)


def create_patent_check_task(
    db: Session,
    settings: Settings,
    user: User,
    title: str | None,
    technical_field: str | None,
    uploads: dict[str, UploadFile | None],
) -> PatentCheckTask:
    """Create a task after validating files and extracting text."""

    required_roles = ("claims", "specification", "drawings")
    for role in required_roles:
        if uploads.get(role) is None:
            raise UserFacingError(f"{FILE_ROLES[role]}为必填项。")

    provided = {role: file for role, file in uploads.items() if file is not None}
    if len(provided) > settings.max_task_files:
        raise UserFacingError(f"单个任务最多上传 {settings.max_task_files} 个文件。")

    extracted_texts: dict[str, str] = {}
    files: list[PatentCheckFile] = []
    stored_paths: list[Path] = []
    try:
        for role, file in provided.items():
            assert file is not None
            content = ensure_pdf_upload(file, settings)
            stored_path = save_upload(content, file.filename or f"{role}.pdf", role, settings)
            stored_paths.append(stored_path)
            text = extract_pdf_text(stored_path)
            extracted_texts[role] = text
            files.append(
                PatentCheckFile(
                    file_role=role,
                    original_filename=file.filename or f"{role}.pdf",
                    stored_path=str(stored_path),
                    content_type=file.content_type,
                    file_size_bytes=len(content),
                    extracted_text_length=len(text),
                    extraction_status="succeeded",
                )
            )

        total_chars = sum(len(text) for text in extracted_texts.values())
        if total_chars > settings.max_total_text_chars:
            raise UserFacingError(
                f"单个任务总输入文本超过 {settings.max_total_text_chars} 个字符限制。"
            )

        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        process_text_path = settings.upload_dir / f"task-input-{uuid4()}.json"
        process_text_path.write_text(
            json.dumps(extracted_texts, ensure_ascii=False),
            encoding="utf-8",
        )

        task = PatentCheckTask(
            user_id=user.id,
            title=title.strip() if title and title.strip() else "未命名审查任务",
            technical_field=(
                technical_field.strip() if technical_field and technical_field.strip() else None
            ),
            claims_text_length=len(extracted_texts.get("claims", "")),
            specification_text_length=len(extracted_texts.get("specification", "")),
            drawings_text_length=len(extracted_texts.get("drawings", "")),
            abstract_text_length=len(extracted_texts.get("abstract", "")),
            process_text_path=str(process_text_path),
            files=files,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        enqueue_patent_check(task.id, settings)
        return get_task_for_user(db, task.id, user)
    except Exception:
        for path in stored_paths:
            path.unlink(missing_ok=True)
        raise


def get_task_for_user(db: Session, task_id: str, user: User) -> PatentCheckTask:
    """Return a task if the current user may access it."""

    stmt = (
        select(PatentCheckTask)
        .options(selectinload(PatentCheckTask.files))
        .where(PatentCheckTask.id == task_id)
    )
    if user.role != "admin":
        stmt = stmt.where(PatentCheckTask.user_id == user.id)
    task = db.scalar(stmt)
    if task is None:
        raise UserFacingError("审查任务不存在或无权访问。", status_code=404)
    return task


def list_tasks_for_user(
    db: Session,
    user: User,
    status: str | None,
    keyword: str | None,
    page: int,
    page_size: int,
) -> tuple[list[PatentCheckTask], int]:
    """List tasks visible to the current user."""

    stmt = select(PatentCheckTask).options(selectinload(PatentCheckTask.files))
    count_stmt = select(func.count(PatentCheckTask.id))
    if user.role != "admin":
        stmt = stmt.where(PatentCheckTask.user_id == user.id)
        count_stmt = count_stmt.where(PatentCheckTask.user_id == user.id)
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
    return list(items), total
