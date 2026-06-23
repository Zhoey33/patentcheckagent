"""这个文件用于定义专利审查任务上传文件的元数据模型。"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PatentCheckFile(Base):
    """Metadata for a PDF uploaded as part of a patent check task."""

    __tablename__ = "patent_check_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("patent_check_tasks.id"), index=True, nullable=False
    )
    file_role: Mapped[str] = mapped_column(String(32), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    extracted_text_length: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    extraction_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    task = relationship("PatentCheckTask", back_populates="files")
