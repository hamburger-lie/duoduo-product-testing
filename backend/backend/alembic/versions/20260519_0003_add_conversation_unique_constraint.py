"""add conversation unique constraint

Revision ID: 20260519_0003
Revises: 20260519_0002
Create Date: 2026-05-19

Replace the plain index ix_conversations_user_evaluation_persona with a
UNIQUE CONSTRAINT on (user_id, evaluation_id, persona_id).

A unique constraint automatically creates a unique index, so the old plain
index is redundant once the constraint exists.
"""

from __future__ import annotations

from alembic import op

# revision identifiers
revision = "20260519_0003"
down_revision = "20260519_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the old plain index first
    op.drop_index(
        "ix_conversations_user_evaluation_persona",
        table_name="conversations",
    )
    # Add the unique constraint (also creates a unique index underneath)
    op.create_unique_constraint(
        "uq_conversations_user_eval_persona",
        "conversations",
        ["user_id", "evaluation_id", "persona_id"],
    )


def downgrade() -> None:
    # Remove the unique constraint
    op.drop_constraint(
        "uq_conversations_user_eval_persona",
        "conversations",
        type_="unique",
    )
    # Re-create the old plain index
    op.create_index(
        "ix_conversations_user_evaluation_persona",
        "conversations",
        ["user_id", "evaluation_id", "persona_id"],
    )
