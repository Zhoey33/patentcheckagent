"""这个文件用于定义专利审查任务的数据模型。"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PatentCheckTask(Base):
    """Asynchronous patent check task submitted by an internal user."""

    __tablename__ = "patent_check_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), default="未命名审查任务", nullable=False)
    technical_field: Mapped[str | None] = mapped_column(String(128), nullable=True)

    claims_text_length: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    specification_text_length: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    drawings_text_length: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    abstract_text_length: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    input_cleanup_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    process_text_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True, nullable=False)
    stage_one_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_report: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="tasks")
    files = relationship(
        "PatentCheckFile",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="PatentCheckFile.created_at",
    )
    model_call_logs = relationship(
        "ModelCallLog",
        back_populates="task",
        cascade="all, delete-orphan",
    )
