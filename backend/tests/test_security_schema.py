from __future__ import annotations

from pathlib import Path

from app.db.base import Base
from app.db.models import load_all_models


def test_security_tables_are_registered_in_metadata() -> None:
    load_all_models()

    assert {
        "customize_requests",
        "user_activity_events",
        "plus_orders",
    }.issubset(Base.metadata.tables.keys())


def test_security_schema_migration_contains_required_tables_and_columns() -> None:
    versions_dir = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    migration_text = "\n".join(
        path.read_text(encoding="utf-8") for path in versions_dir.glob("*.py")
    )

    for required in (
        "customize_requests",
        "user_activity_events",
        "plus_orders",
        "is_plus",
        "plus_expires_at",
    ):
        assert required in migration_text
