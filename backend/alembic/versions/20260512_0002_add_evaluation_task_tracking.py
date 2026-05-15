"""add evaluation task tracking

Revision ID: 20260512_0002
Revises: 645bc8242179
Create Date: 2026-05-12 11:10:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260512_0002"
down_revision: str | None = "645bc8242179"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        "evaluations",
        sa.Column("task_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "evaluations",
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "evaluations",
        sa.Column("run_mode", sa.String(length=16), nullable=True),
    )
    op.create_index(
        op.f("ix_evaluations_task_id"),
        "evaluations",
        ["task_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(op.f("ix_evaluations_task_id"), table_name="evaluations")
    op.drop_column("evaluations", "run_mode")
    op.drop_column("evaluations", "queued_at")
    op.drop_column("evaluations", "task_id")
