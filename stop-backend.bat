@echo off
chcp 65001 >nul
echo 停止后端 Docker 服务...
cd /d "%~dp0backend\backend"
docker compose down
echo 已停止。
pause
