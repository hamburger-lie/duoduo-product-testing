"""add answer summary_comment column

Revision ID: 20260513_0001
Revises: 20260512_0002
Create Date: 2026-05-13 10:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260513_0001"
down_revision: str | None = "20260512_0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "answers",
        sa.Column("summary_comment", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("answers", "summary_comment")
