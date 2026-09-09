@echo off
chcp 65001 >nul
REM ============ 一键同时启动后端 + 前端（两个独立窗口）============
cd /d "%~dp0"
start "Agent Backend :8000"  cmd /k start_backend.bat
timeout /t 5 /nobreak >nul
start "Agent Frontend :8501" cmd /k start_frontend.bat
echo.
echo 后端 http://localhost:8000/docs   前端 http://localhost:8501
echo 关闭时请分别关闭两个窗口。
