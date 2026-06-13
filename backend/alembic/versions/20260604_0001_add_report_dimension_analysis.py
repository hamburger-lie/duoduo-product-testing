"""add report dimension_analysis columns

Revision ID: 20260604_0001
Revises: 20260603_0001
Create Date: 2026-06-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260604_0001"
down_revision: str | None = "20260603_0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE reports ADD COLUMN IF NOT EXISTS dimension_analysis JSONB"
    )
    op.execute(
        "ALTER TABLE reports ADD COLUMN IF NOT EXISTS dimension_analysis_status VARCHAR(20)"
    )
    # Drop deep_analysis if it was ever added (may not exist — IF EXISTS is safe)
    op.execute(
        "ALTER TABLE reports DROP COLUMN IF EXISTS deep_analysis"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE reports DROP COLUMN IF EXISTS dimension_analysis_status")
    op.execute("ALTER TABLE reports DROP COLUMN IF EXISTS dimension_analysis")
