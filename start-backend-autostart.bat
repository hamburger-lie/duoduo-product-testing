@echo off
chcp 65001 >nul

cd /d "%~dp0backend\backend"

:: 等待 Docker Desktop 就绪（开机后 Docker 可能还没启动）
:wait_docker
docker info >nul 2>&1
if %errorlevel% neq 0 (
    timeout /t 5 /nobreak >nul
    goto wait_docker
)

:: 启动 Docker 依赖服务
docker compose up -d postgres redis qdrant >nul 2>&1

:: 等待数据库就绪
timeout /t 10 /nobreak >nul

:: 执行数据库迁移
uv run alembic upgrade head >nul 2>&1

:: 导入种子数据
uv run python scripts/seed_personas.py >nul 2>&1

:: 在最小化窗口中启动 API 服务器
start /min "测品官后端" uv run uvicorn app.main:app --host 0.0.0.0 --port 18000
