"""这个文件用于在 Worker 启动前恢复因进程中断而遗留的运行中任务。"""

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.models.patent_check_task import PatentCheckTask

logger = logging.getLogger(__name__)


def recover_stale_running_tasks(
    db: Session,
    settings: Settings,
    now: datetime | None = None,
) -> int:
    """Mark expired running tasks as failed so users can retry after Worker restarts."""

    current_time = now or datetime.now(UTC)
    cutoff = current_time - timedelta(seconds=max(settings.codex_timeout_seconds, 60))
    tasks = db.scalars(
        select(PatentCheckTask).where(
            PatentCheckTask.status == "running",
            PatentCheckTask.started_at.is_not(None),
            PatentCheckTask.started_at <= cutoff,
        )
    ).all()
    message = "Worker 重启后任务未完成，已标记为失败，可点击重试。"
    for task in tasks:
        task.status = "failed"
        task.progress_message = message
        task.error_message = message
        task.finished_at = current_time
        available = bool(task.files) and all(
            file.stored_path and Path(file.stored_path).is_file() for file in task.files
        )
        task.input_cleanup_status = "retryable" if available else "cleaned"
    if tasks:
        db.commit()
    logger.info("stale_running_tasks_recovered count=%s", len(tasks))
    return len(tasks)


def main() -> None:
    """Recover stale running tasks using the configured database."""

    settings = get_settings()
    configure_logging(settings)
    with SessionLocal() as db:
        recover_stale_running_tasks(db, settings)


if __name__ == "__main__":
    main()
