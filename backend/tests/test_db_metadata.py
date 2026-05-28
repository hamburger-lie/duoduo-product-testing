from __future__ import annotations

from app.db.base import Base
from app.db.models import load_all_models


def test_sqlalchemy_metadata_loads_all_core_tables() -> None:
    load_all_models()

    expected_tables = {
        "answers",
        "conversation_messages",
        "conversations",
        "credit_recharge_orders",
        "credit_transactions",
        "evaluations",
        "personas",
        "products",
        "prompt_versions",
        "reports",
        "surveys",
        "users",
    }

    assert expected_tables.issubset(Base.metadata.tables.keys())
