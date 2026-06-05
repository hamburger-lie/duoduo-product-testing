@echo off
cd /d "%~dp0backend"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 "') do taskkill /F /PID %%a >nul 2>&1
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info >> uvicorn-8000.log 2>> uvicorn-8000.err.log
