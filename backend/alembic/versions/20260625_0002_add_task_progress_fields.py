"""这个文件用于为专利审查任务增加进度展示字段。

Revision ID: 20260625_0002
Revises: 20260623_0001
Create Date: 2026-06-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260625_0002"
down_revision: str | None = "20260623_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "patent_check_tasks",
        sa.Column(
            "progress_stage",
            sa.String(length=32),
            nullable=False,
            server_default="queued",
        ),
    )
    op.add_column(
        "patent_check_tasks",
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="5"),
    )
    op.add_column(
        "patent_check_tasks",
        sa.Column(
            "progress_message",
            sa.String(length=255),
            nullable=False,
            server_default="任务已提交，等待审查队列调度。",
        ),
    )


def downgrade() -> None:
    op.drop_column("patent_check_tasks", "progress_message")
    op.drop_column("patent_check_tasks", "progress_percent")
    op.drop_column("patent_check_tasks", "progress_stage")
