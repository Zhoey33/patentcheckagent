"""这个文件用于定义专利审查任务执行过程事件的数据模型。"""

import json
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PatentCheckEvent(Base):
    """A user-visible event emitted while Codex executes a patent check task."""

    __tablename__ = "patent_check_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("patent_check_tasks.id"), index=True, nullable=False
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    task = relationship("PatentCheckTask", back_populates="events")

    @property
    def content(self) -> str | None:
        """Return streamed Markdown content carried by report events."""

        if self.event_type not in {"report_snapshot", "report_delta"} or not self.raw_payload:
            return None
        try:
            payload = json.loads(self.raw_payload)
        except json.JSONDecodeError:
            return None
        content = payload.get("content")
        return content if isinstance(content, str) else None
