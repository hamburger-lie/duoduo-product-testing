@echo off
chcp 65001 >nul
title 测品官开发服务

echo ====================================
echo  启动测品官开发服务
echo ====================================
echo.

:: 启动后端 (port 18000)
echo [1/2] 启动测品官后端 (port 18000)...
start "测品官后端" cmd /k "cd /d D:\soul\backend\backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 18000 --reload"

:: 等待一秒再启动第二个
timeout /t 1 /nobreak >nul

:: 启动报告模板工具 (port 5678)
echo [2/2] 启动报告模板工具 (port 5678)...
start "报告模板工具" cmd /k "cd /d D:\AI报告生成模板工具 && python proxy.py"

echo.
echo 两个服务已在独立窗口启动，关闭本窗口不影响服务运行。
echo.
pause
