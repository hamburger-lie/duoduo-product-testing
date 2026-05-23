"""add credit recharge orders

Revision ID: 20260523_0001
Revises: 20260521_0001
Create Date: 2026-05-23 15:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260523_0001"
down_revision = "20260521_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create durable credit recharge orders."""

    op.create_table(
        "credit_recharge_orders",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("order_no", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_transaction_id", sa.String(length=128), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("amount_yuan", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_callback", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_credit_recharge_orders_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_credit_recharge_orders")),
        sa.UniqueConstraint("order_no", name=op.f("uq_credit_recharge_orders_order_no")),
        sa.UniqueConstraint(
            "provider_transaction_id",
            name=op.f("uq_credit_recharge_orders_provider_transaction_id"),
        ),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_credit_recharge_orders_user_idempotency_key",
        ),
    )
    op.create_index(
        op.f("ix_credit_recharge_orders_user_id"),
        "credit_recharge_orders",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_credit_recharge_orders_user_created_at_desc",
        "credit_recharge_orders",
        ["user_id", sa.text("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    """Drop durable credit recharge orders."""

    op.drop_index(
        "ix_credit_recharge_orders_user_created_at_desc",
        table_name="credit_recharge_orders",
    )
    op.drop_index(
        op.f("ix_credit_recharge_orders_user_id"),
        table_name="credit_recharge_orders",
    )
    op.drop_table("credit_recharge_orders")
