"""add category_norms table and evaluation benchmark_product_ids

品类常模池：每个完成的评测按品类留一条聚合分数，
报告用它输出「本品在同品类的百分位」（norm-referenced scoring）。

Revision ID: 20260709_0001
Revises: 20260604_0001, 645bc8242179 (merges heads)
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260709_0001"
down_revision: str | tuple[str, ...] | None = ("20260604_0001", "645bc8242179")
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS category_norms (
            id BIGINT PRIMARY KEY,
            evaluation_id BIGINT NOT NULL REFERENCES evaluations (id),
            product_id BIGINT NOT NULL REFERENCES products (id),
            user_id BIGINT NOT NULL REFERENCES users (id),
            category VARCHAR(32) NOT NULL,
            sub_category VARCHAR(64),
            intent_avg DOUBLE PRECISION NOT NULL,
            intent_distribution JSONB NOT NULL DEFAULT '{}'::jsonb,
            sample_size INTEGER NOT NULL DEFAULT 0,
            is_benchmark BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_category_norms_category ON category_norms (category)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_category_norms_evaluation_id "
        "ON category_norms (evaluation_id)"
    )
    op.execute(
        "ALTER TABLE evaluations ADD COLUMN IF NOT EXISTS "
        "benchmark_product_ids JSONB NOT NULL DEFAULT '[]'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE evaluations DROP COLUMN IF EXISTS benchmark_product_ids")
    op.execute("DROP TABLE IF EXISTS category_norms")
