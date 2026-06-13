"""security hardening schema

Revision ID: 20260603_0001
Revises: 20260526_0001
Create Date: 2026-06-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


revision: str = "20260603_0001"
down_revision: str | None = "20260526_0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

jsonb_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    # --- users columns (idempotent: server may already have these from manual ALTER) ---
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_plus BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS plus_expires_at TIMESTAMPTZ")

    # --- plus_orders (idempotent: table may already exist from manual CREATE) ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS plus_orders (
            id BIGSERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at TIMESTAMPTZ,
            user_id BIGINT NOT NULL REFERENCES users(id),
            out_trade_no VARCHAR(64) NOT NULL,
            amount_fen INTEGER NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'pending',
            paid_at TIMESTAMPTZ
        )
    """)
    # Add deleted_at if table existed before this migration (manual creation omitted it)
    op.execute("ALTER TABLE plus_orders ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ix_plus_orders_out_trade_no
        ON plus_orders (out_trade_no)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_plus_orders_user_created_at_desc
        ON plus_orders (user_id, created_at DESC)
    """)

    # --- customize_requests ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS customize_requests (
            id BIGSERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at TIMESTAMPTZ,
            user_id BIGINT NOT NULL REFERENCES users(id),
            name VARCHAR(32) NOT NULL,
            phone VARCHAR(32) NOT NULL,
            company VARCHAR(100) NOT NULL,
            requirement TEXT NOT NULL,
            ip VARCHAR(64),
            user_agent VARCHAR(512),
            status VARCHAR(16) NOT NULL DEFAULT 'submitted'
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_customize_requests_user_created_at
        ON customize_requests (user_id, created_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_customize_requests_status
        ON customize_requests (status)
    """)

    # --- user_activity_events ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_activity_events (
            id BIGSERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at TIMESTAMPTZ,
            user_id BIGINT REFERENCES users(id),
            event_type VARCHAR(64) NOT NULL,
            path VARCHAR(256),
            method VARCHAR(8),
            request_id VARCHAR(64),
            ip VARCHAR(64),
            user_agent VARCHAR(512),
            metadata JSONB
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_user_activity_events_user_created_at
        ON user_activity_events (user_id, created_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_user_activity_events_event_type
        ON user_activity_events (event_type)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_user_activity_events_request_id
        ON user_activity_events (request_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_user_activity_events_request_id")
    op.execute("DROP INDEX IF EXISTS ix_user_activity_events_event_type")
    op.execute("DROP INDEX IF EXISTS ix_user_activity_events_user_created_at")
    op.execute("DROP TABLE IF EXISTS user_activity_events")

    op.execute("DROP INDEX IF EXISTS ix_customize_requests_status")
    op.execute("DROP INDEX IF EXISTS ix_customize_requests_user_created_at")
    op.execute("DROP TABLE IF EXISTS customize_requests")

    op.execute("DROP INDEX IF EXISTS ix_plus_orders_out_trade_no")
    op.execute("DROP INDEX IF EXISTS ix_plus_orders_user_created_at_desc")
    op.execute("DROP TABLE IF EXISTS plus_orders")

    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS plus_expires_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS is_plus")
