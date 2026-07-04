"""这个文件用于定义专利审查任务的数据模型。"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

PROGRESS_STEPS = [
    ("queued", "排队等待执行", 5),
    ("preparing", "准备审查材料", 15),
    ("stage_one", "第一阶段：权利要求书检查", 40),
    ("stage_two", "第二阶段：说明书/附图/摘要检查", 75),
    ("finalizing", "整理最终报告", 92),
    ("completed", "审查完成", 100),
]

PROGRESS_STAGE_ORDER = {step[0]: index for index, step in enumerate(PROGRESS_STEPS)}
PROGRESS_STAGE_DEFAULTS = {step[0]: step[2] for step in PROGRESS_STEPS}


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
    progress_stage: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    progress_percent: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    progress_message: Mapped[str] = mapped_column(
        String(255),
        default="任务已提交，等待审查队列调度。",
        nullable=False,
    )
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
    events = relationship(
        "PatentCheckEvent",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="PatentCheckEvent.id",
    )

    @property
    def progress_steps(self) -> list[dict[str, str]]:
        """Return ordered progress nodes for API consumers."""

        current_stage = self.progress_stage or infer_progress_stage(self.status)
        current_index = PROGRESS_STAGE_ORDER.get(current_stage, 0)
        steps = []
        for index, (key, label, _) in enumerate(PROGRESS_STEPS):
            if self.status == "failed" and index == current_index:
                step_status = "failed"
            elif index < current_index or self.status == "succeeded":
                step_status = "done"
            elif index == current_index:
                step_status = "running" if self.status in {"pending", "running"} else "pending"
            else:
                step_status = "pending"
            steps.append({"key": key, "label": label, "status": step_status})
        return steps


def infer_progress_stage(status: str) -> str:
    """Map task status to a stable progress stage for older rows."""

    if status == "succeeded":
        return "completed"
    if status == "running":
        return "preparing"
    return "queued"
