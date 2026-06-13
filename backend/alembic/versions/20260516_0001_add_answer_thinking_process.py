"""add answer thinking_process column

Revision ID: 20260516_0001
Revises: 20260513_0001
Create Date: 2026-05-16 10:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260516_0001"
down_revision: str | None = "20260513_0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "answers",
        sa.Column("thinking_process", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("answers", "thinking_process")
