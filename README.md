# soul-unified

测品官 (CPG product-testing) monorepo.

## Structure

```
backend/    Python backend (FastAPI app, Alembic migrations, Celery tasks, tests, deploy)
frontend/   WeChat mini-program (测品官小程序)
docs/        Project documentation, runbooks, mockups, promotion plans
DEPLOY.md   Deployment guide
```

## Backend

```
cd backend
uv sync                 # install deps (pyproject.toml / uv.lock)
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -c "import app.main"   # smoke import
```

Key paths: `backend/app/` (routers, services, ai, db, schemas), `backend/alembic/`,
`backend/tests/`, `backend/scripts/` (Python tooling), `backend/Dockerfile`,
`backend/docker-compose.yml`.

## Frontend

WeChat mini-program. Open `frontend/` as the project root in 微信开发者工具
(`project.config.json` lives at `frontend/`). Pages are registered in `frontend/app.json`.

## Notes

- Secrets (`.env`, `project.private.config.json`, `*.pem`) are gitignored — never commit them.
- This repo was rebuilt from a clean baseline; prior git history was intentionally discarded.
