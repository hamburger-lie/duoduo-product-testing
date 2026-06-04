"""add report dimension_analysis columns

Revision ID: 20260528_0001
Revises: 20260526_0001
Create Date: 2026-05-28 12:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260528_0001"
down_revision: str | None = "20260526_0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "reports",
        sa.Column(
            "dimension_analysis",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "reports",
        sa.Column("dimension_analysis_status", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("reports", "dimension_analysis_status")
    op.drop_column("reports", "dimension_analysis")
