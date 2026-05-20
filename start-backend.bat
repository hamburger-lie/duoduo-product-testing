@echo off
chcp 65001 >nul
echo ============================
echo  测品官后端启动脚本
echo ============================

cd /d "%~dp0backend\backend"

echo [1/4] 启动 Docker 依赖服务 (postgres + redis + qdrant)...
docker compose up -d postgres redis qdrant
if %errorlevel% neq 0 (
    echo 错误：Docker 启动失败，请确认 Docker Desktop 已运行
    pause
    exit /b 1
)

echo 等待数据库就绪...
timeout /t 8 /nobreak >nul

echo [2/4] 执行数据库迁移...
uv run alembic upgrade head
if %errorlevel% neq 0 (
    echo 错误：数据库迁移失败
    pause
    exit /b 1
)

echo [3/4] 导入种子数据 (Persona)...
uv run python scripts/seed_personas.py

echo [4/4] 启动 API 服务器 (http://127.0.0.1:18000) ...
echo.
echo API 文档地址: http://127.0.0.1:18000/docs
echo 按 Ctrl+C 停止服务
echo.
uv run uvicorn app.main:app --host 0.0.0.0 --port 18000 --reload

pause
