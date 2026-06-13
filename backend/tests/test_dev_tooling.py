from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_alembic_ini_uses_generic_fallback_port() -> None:
    """alembic.ini should not bake in the local Docker port."""

    content = (ROOT / "alembic.ini").read_text(encoding="utf-8")
    assert "localhost:5433" not in content
    assert "localhost:5432" in content


def test_docker_compose_defines_local_dependencies() -> None:
    """Local compose should expose postgres/redis/qdrant for development."""

    content = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    for service in ["postgres:", "redis:", "qdrant:"]:
        assert service in content
    assert "5433:5432" in content
    assert "6380:6379" in content
    assert "postgres:15" in content
    assert "redis:7" in content
    assert "qdrant/qdrant" in content
    assert "healthcheck:" in content


def test_env_example_uses_local_dependency_ports() -> None:
    """Local host ports should avoid common PostgreSQL/Redis conflicts."""

    content = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/duoduo" in content
    assert "REDIS_URL=redis://localhost:6380/0" in content


def test_dockerfile_and_dockerignore_exist() -> None:
    """Container build inputs should be present and avoid local artifacts."""

    dockerfile = ROOT / "Dockerfile"
    dockerignore = ROOT / ".dockerignore"
    assert dockerfile.exists()
    assert dockerignore.exists()
    ignore_content = dockerignore.read_text(encoding="utf-8")
    assert ".venv" in ignore_content
    assert ".env" in ignore_content


def test_dev_check_script_exists_with_expected_checks() -> None:
    """dev_check.py should cover the local readiness checks used for handoff."""

    content = (ROOT / "scripts" / "dev_check.py").read_text(encoding="utf-8")
    for marker in [
        "DEV_CHECK_OK",
        "check_python_and_uv",
        "check_database",
        "check_alembic",
        "check_seed_personas",
        "check_health",
        "check_openapi_export",
    ]:
        assert marker in content


def test_e2e_mock_flow_matches_current_api_shapes() -> None:
    """The live E2E script should match current answers/report response shapes."""

    content = (ROOT / "scripts" / "e2e_mock_flow.py").read_text(encoding="utf-8")
    assert 'len(resp.json()["items"])' not in content
    assert '["metrics"]["overall_score"]' not in content
    assert '["metrics"]["overall_intent"]["average"]' in content
