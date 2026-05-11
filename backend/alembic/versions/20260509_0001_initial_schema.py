"""initial schema

Revision ID: 20260509_0001
Revises:
Create Date: 2026-05-09 15:20:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260509_0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "prompt_versions",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=16), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prompt_versions")),
        sa.UniqueConstraint("name", "version", name="uq_prompt_versions_name_version"),
    )

    op.create_table(
        "users",
        sa.Column("openid", sa.String(length=64), nullable=False),
        sa.Column("unionid", sa.String(length=64), nullable=True),
        sa.Column("nickname", sa.String(length=64), nullable=True),
        sa.Column("avatar_url", sa.String(length=512), nullable=True),
        sa.Column("role_type", sa.String(length=16), nullable=True),
        sa.Column("credit_balance", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("openid", name=op.f("uq_users_openid")),
    )
    op.create_index("ix_users_openid", "users", ["openid"], unique=False)
    op.create_index("ix_users_unionid", "users", ["unionid"], unique=False)

    op.create_table(
        "credit_transactions",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(length=32), nullable=True),
        sa.Column("ref_type", sa.String(length=32), nullable=True),
        sa.Column("ref_id", sa.BigInteger(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_credit_transactions_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_credit_transactions")),
    )
    op.create_index(
        "ix_credit_transactions_user_created_at_desc",
        "credit_transactions",
        ["user_id", sa.text("created_at DESC")],
        unique=False,
    )

    op.create_table(
        "personas",
        sa.Column("owner_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("avatar", sa.String(length=64), nullable=True),
        sa.Column("age", sa.SmallInteger(), nullable=False),
        sa.Column("gender", sa.String(length=8), nullable=False),
        sa.Column("city", sa.String(length=32), nullable=False),
        sa.Column("city_tier", sa.SmallInteger(), nullable=True),
        sa.Column("occupation", sa.String(length=64), nullable=True),
        sa.Column("income_monthly", sa.Integer(), nullable=True),
        sa.Column("ocean_o", sa.SmallInteger(), nullable=True),
        sa.Column("ocean_c", sa.SmallInteger(), nullable=True),
        sa.Column("ocean_e", sa.SmallInteger(), nullable=True),
        sa.Column("ocean_a", sa.SmallInteger(), nullable=True),
        sa.Column("ocean_n", sa.SmallInteger(), nullable=True),
        sa.Column("persona_tag", sa.String(length=32), nullable=True),
        sa.Column("profile", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("categories", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_critical", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_personas_owner_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_personas")),
    )
    op.create_index(
        "ix_personas_categories_gin",
        "personas",
        ["categories"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index("ix_personas_is_critical", "personas", ["is_critical"], unique=False)
    op.create_index("ix_personas_owner_id", "personas", ["owner_id"], unique=False)
    op.create_index("ix_personas_persona_tag", "personas", ["persona_tag"], unique=False)

    op.create_table(
        "products",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=True),
        sa.Column("sub_category", sa.String(length=64), nullable=True),
        sa.Column("brand", sa.String(length=64), nullable=True),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("price_range", sa.String(length=32), nullable=True),
        sa.Column("target_channel", sa.String(length=32), nullable=True),
        sa.Column("image_urls", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ai_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_products_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
    )
    op.create_index("ix_products_category", "products", ["category"], unique=False)
    op.create_index(
        "ix_products_user_created_at_desc",
        "products",
        ["user_id", sa.text("created_at DESC")],
        unique=False,
    )

    op.create_table(
        "evaluations",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("survey_id", sa.BigInteger(), nullable=True),
        sa.Column("selected_persona_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.SmallInteger(), nullable=False),
        sa.Column("credit_cost", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_evaluations_product_id_products"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_evaluations_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluations")),
    )
    op.create_index("ix_evaluations_status", "evaluations", ["status"], unique=False)
    op.create_index(
        "ix_evaluations_user_created_at_desc",
        "evaluations",
        ["user_id", sa.text("created_at DESC")],
        unique=False,
    )

    op.create_table(
        "surveys",
        sa.Column("evaluation_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("questions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("generated_by", sa.String(length=16), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["evaluation_id"],
            ["evaluations.id"],
            name=op.f("fk_surveys_evaluation_id_evaluations"),
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_surveys_product_id_products"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_surveys")),
    )
    op.create_foreign_key(
        op.f("fk_evaluations_survey_id_surveys"),
        "evaluations",
        "surveys",
        ["survey_id"],
        ["id"],
    )

    op.create_table(
        "answers",
        sa.Column("evaluation_id", sa.BigInteger(), nullable=False),
        sa.Column("survey_id", sa.BigInteger(), nullable=False),
        sa.Column("persona_id", sa.BigInteger(), nullable=False),
        sa.Column("answers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("overall_intent", sa.SmallInteger(), nullable=True),
        sa.Column("sentiment", sa.String(length=16), nullable=True),
        sa.Column("token_input", sa.Integer(), nullable=True),
        sa.Column("token_output", sa.Integer(), nullable=True),
        sa.Column("cost_yuan", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["evaluation_id"],
            ["evaluations.id"],
            name=op.f("fk_answers_evaluation_id_evaluations"),
        ),
        sa.ForeignKeyConstraint(
            ["persona_id"],
            ["personas.id"],
            name=op.f("fk_answers_persona_id_personas"),
        ),
        sa.ForeignKeyConstraint(
            ["survey_id"],
            ["surveys.id"],
            name=op.f("fk_answers_survey_id_surveys"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_answers")),
        sa.UniqueConstraint("evaluation_id", "persona_id", name="uq_answers_evaluation_persona"),
    )
    op.create_index(
        "ix_answers_persona_created_at_desc",
        "answers",
        ["persona_id", sa.text("created_at DESC")],
        unique=False,
    )

    op.create_table(
        "conversations",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("evaluation_id", sa.BigInteger(), nullable=False),
        sa.Column("persona_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["evaluation_id"],
            ["evaluations.id"],
            name=op.f("fk_conversations_evaluation_id_evaluations"),
        ),
        sa.ForeignKeyConstraint(
            ["persona_id"],
            ["personas.id"],
            name=op.f("fk_conversations_persona_id_personas"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_conversations_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
    )
    op.create_index(
        "ix_conversations_user_evaluation_persona",
        "conversations",
        ["user_id", "evaluation_id", "persona_id"],
        unique=False,
    )

    op.create_table(
        "conversation_messages",
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_input", sa.Integer(), nullable=True),
        sa.Column("token_output", sa.Integer(), nullable=True),
        sa.Column("cost_yuan", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_conversation_messages_conversation_id_conversations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversation_messages")),
    )
    op.create_index(
        "ix_conversation_messages_conversation_created_at",
        "conversation_messages",
        ["conversation_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "reports",
        sa.Column("evaluation_id", sa.BigInteger(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("top_pros", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("top_cons", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("persona_segments", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("pdf_url", sa.String(length=512), nullable=True),
        sa.Column("share_token", sa.String(length=32), nullable=True),
        sa.Column("id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["evaluation_id"],
            ["evaluations.id"],
            name=op.f("fk_reports_evaluation_id_evaluations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reports")),
        sa.UniqueConstraint("evaluation_id", name="uq_reports_evaluation_id"),
        sa.UniqueConstraint("share_token", name="uq_reports_share_token"),
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_table("reports")
    op.drop_index(
        "ix_conversation_messages_conversation_created_at",
        table_name="conversation_messages",
    )
    op.drop_table("conversation_messages")
    op.drop_index("ix_conversations_user_evaluation_persona", table_name="conversations")
    op.drop_table("conversations")
    op.drop_index("ix_answers_persona_created_at_desc", table_name="answers")
    op.drop_table("answers")
    op.drop_constraint(op.f("fk_evaluations_survey_id_surveys"), "evaluations", type_="foreignkey")
    op.drop_table("surveys")
    op.drop_index("ix_evaluations_user_created_at_desc", table_name="evaluations")
    op.drop_index("ix_evaluations_status", table_name="evaluations")
    op.drop_table("evaluations")
    op.drop_index("ix_products_user_created_at_desc", table_name="products")
    op.drop_index("ix_products_category", table_name="products")
    op.drop_table("products")
    op.drop_index("ix_personas_persona_tag", table_name="personas")
    op.drop_index("ix_personas_owner_id", table_name="personas")
    op.drop_index("ix_personas_is_critical", table_name="personas")
    op.drop_index("ix_personas_categories_gin", table_name="personas", postgresql_using="gin")
    op.drop_table("personas")
    op.drop_index("ix_credit_transactions_user_created_at_desc", table_name="credit_transactions")
    op.drop_table("credit_transactions")
    op.drop_index("ix_users_unionid", table_name="users")
    op.drop_index("ix_users_openid", table_name="users")
    op.drop_table("users")
    op.drop_table("prompt_versions")
