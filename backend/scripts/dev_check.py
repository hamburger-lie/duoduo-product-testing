"""Local development readiness check.

Usage:
    uv run python scripts/dev_check.py
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.db.models.persona import Persona

ROOT = Path(__file__).resolve().parent.parent
PROJECT_DOCS = ROOT.parent / "docs"
API_BASE_URL = "http://127.0.0.1:8000"


def _line(message: str) -> None:
    sys.stdout.write(f"{message}\n")


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def check_python_and_uv() -> bool:
    """Check Python version and uv availability."""

    ok = True
    version = sys.version_info
    if version.major == 3 and version.minor == 11:
        _line(f"[ok] Python {version.major}.{version.minor}.{version.micro}")
    else:
        _line(f"[fail] Python 3.11 required, got {version.major}.{version.minor}")
        ok = False

    uv_path = shutil.which("uv")
    if uv_path:
        _line(f"[ok] uv found: {uv_path}")
    else:
        _line("[fail] uv not found on PATH")
        ok = False
    return ok


async def check_database() -> bool:
    """Check that DATABASE_URL is reachable."""

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("select 1"))
            if result.scalar_one() == 1:
                _line("[ok] database connection")
                return True
    except Exception as exc:
        _line(f"[fail] database connection: {exc}")
        return False
    finally:
        await engine.dispose()
    _line("[fail] database connection returned unexpected result")
    return False


def check_alembic() -> bool:
    """Check Alembic can report current revision and head."""

    current = _run(["uv", "run", "alembic", "current"])
    heads = _run(["uv", "run", "alembic", "heads"])
    if current.returncode == 0 and heads.returncode == 0:
        current_text = current.stdout.strip() or "(none)"
        heads_text = heads.stdout.strip() or "(none)"
        _line(f"[ok] alembic current: {current_text}")
        _line(f"[ok] alembic head: {heads_text}")
        return True

    _line("[fail] alembic current/head")
    if current.stderr:
        _line(current.stderr.strip())
    if heads.stderr:
        _line(heads.stderr.strip())
    return False


async def check_seed_personas() -> bool:
    """Check at least five active personas exist for front-end flow testing."""

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                select(func.count(Persona.id)).where(Persona.deleted_at.is_(None))
            )
            count = int(result.scalar_one())
            if count >= 5:
                _line(f"[ok] seed personas: {count}")
                return True
            _line(
                "[fail] seed personas: "
                f"{count}; run `uv run python scripts/seed_personas.py`"
            )
            return False
    except Exception as exc:
        _line(f"[fail] seed personas query: {exc}")
        return False
    finally:
        await engine.dispose()


async def check_health() -> bool:
    """Check API health endpoints if the local API server is running."""

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            live = await client.get(f"{API_BASE_URL}/health/live")
            ready = await client.get(f"{API_BASE_URL}/health/ready")
    except httpx.RequestError:
        _line(
            "[skip] HTTP health: API not running; "
            "start with `uv run uvicorn app.main:app --reload`"
        )
        return True

    if live.status_code == 200 and ready.status_code == 200:
        _line("[ok] HTTP health live/ready")
        return True

    _line(f"[fail] HTTP health: live={live.status_code}, ready={ready.status_code}")
    return False


def check_openapi_export() -> bool:
    """Check OpenAPI can be exported to docs/openapi.v0.1.json."""

    from scripts.export_openapi import main as export_openapi

    try:
        export_openapi()
    except Exception as exc:
        _line(f"[fail] openapi export: {exc}")
        return False

    output = PROJECT_DOCS / "openapi.v0.1.json"
    if output.exists() and output.stat().st_size > 0:
        _line(f"[ok] openapi export: {output}")
        return True
    _line("[fail] openapi export did not produce docs/openapi.v0.1.json")
    return False


async def main() -> int:
    """Run all local development checks."""

    checks = [
        check_python_and_uv(),
        await check_database(),
        check_alembic(),
        await check_seed_personas(),
        await check_health(),
        check_openapi_export(),
    ]
    if all(checks):
        _line("DEV_CHECK_OK")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
