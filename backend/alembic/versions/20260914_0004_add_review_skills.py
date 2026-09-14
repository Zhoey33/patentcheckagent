"""保存管理员管理的 skill 和任务使用的完整快照。"""

import sqlalchemy as sa

from alembic import op

revision = "20260914_0004"
down_revision = "20260629_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_skills",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("description", sa.String(1024), nullable=False),
        sa.Column("files", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_review_skills_default",
        "review_skills",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default = true"),
        sqlite_where=sa.text("is_default = 1"),
    )
    op.add_column("patent_check_tasks", sa.Column("skill_snapshot", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("patent_check_tasks", "skill_snapshot")
    op.drop_table("review_skills")
