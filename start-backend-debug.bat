@echo off
set BACKEND_DIR=%~dp0backend\backend

echo === Backend Startup ===
echo.

if not exist "%BACKEND_DIR%" (
    echo ERROR: Directory not found: %BACKEND_DIR%
    pause
    exit /b 1
)

pushd "%BACKEND_DIR%"
echo Working dir: %CD%
echo.

echo [1] Checking Docker...
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Docker Desktop is not running.
    echo Please open Docker Desktop and wait for the whale icon to stop animating.
    popd & pause & exit /b 1
)
echo Docker OK

echo.
echo [2] Starting postgres + redis + qdrant...
docker compose up -d postgres redis qdrant
if %errorlevel% neq 0 (
    echo ERROR: docker compose failed. See above for details.
    popd & pause & exit /b 1
)
echo Services started.

echo.
echo [3] Waiting 8s for database to be ready...
timeout /t 8 /nobreak >nul

echo.
echo [4] Running database migrations...
uv run alembic upgrade head
if %errorlevel% neq 0 (
    echo ERROR: Migration failed.
    popd & pause & exit /b 1
)
echo Migrations OK.

echo.
echo [5] Seeding persona data...
uv run python scripts/seed_personas.py
echo Seed done.

echo.
echo =========================================
echo  API: http://127.0.0.1:18000
echo  Docs: http://127.0.0.1:18000/docs
echo  Ctrl+C to stop
echo =========================================
echo.

uv run uvicorn app.main:app --host 127.0.0.1 --port 18000 --reload

popd
pause
