"""add survey unique constraint on evaluation_id

Revision ID: 20260519_0002
Revises: 20260519_0001
Create Date: 2026-05-19

Add a UNIQUE constraint on surveys.evaluation_id to enforce at the DB level
that each evaluation may only have one survey (business rule already enforced
at the application layer via Evaluation.survey_id).
"""

from __future__ import annotations

from alembic import op

# revision identifiers
revision = "20260519_0002"
down_revision = "20260519_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_surveys_evaluation_id",
        "surveys",
        ["evaluation_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_surveys_evaluation_id",
        "surveys",
        type_="unique",
    )
