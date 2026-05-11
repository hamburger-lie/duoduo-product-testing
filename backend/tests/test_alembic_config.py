from __future__ import annotations

from pathlib import Path


def test_alembic_scaffold_exists() -> None:
    backend_root = Path(__file__).resolve().parent.parent

    assert (backend_root / "alembic.ini").is_file()
    assert (backend_root / "alembic" / "env.py").is_file()
    assert (backend_root / "alembic" / "versions").is_dir()
