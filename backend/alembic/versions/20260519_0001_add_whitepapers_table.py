"""add whitepapers table

Revision ID: 20260519_0001
Revises: 20260513_0001
Create Date: 2026-05-19 10:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260519_0001"
down_revision: str | None = "20260516_0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "whitepapers",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("evaluation_id", sa.BigInteger(), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("product_description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("markdown", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["evaluation_id"],
            ["evaluations.id"],
            name="fk_whitepapers_evaluation_id_evaluations",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_whitepapers"),
        sa.UniqueConstraint("evaluation_id", name="uq_whitepapers_evaluation_id"),
    )


def downgrade() -> None:
    op.drop_table("whitepapers")
