"""add user phone number

Revision ID: 20260526_0001
Revises: 20260521_0001, 645bc8242179
Create Date: 2026-05-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260526_0001"
down_revision = ("20260521_0001", "645bc8242179")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone_number", sa.String(length=32), nullable=True))
    op.create_index("ix_users_phone_number", "users", ["phone_number"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_phone_number", table_name="users")
    op.drop_column("users", "phone_number")
