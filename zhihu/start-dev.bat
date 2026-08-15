@echo off
chcp 65001 >nul
title 职护开发环境启动器

echo ========================================
echo   职护 - 开发环境启动
echo ========================================
echo.

REM 启动后端
echo [1/2] 启动后端服务 (FastAPI on port 8000)...
start "职护后端" cmd /k "cd /d D:\code\zhihu\zhihu-backend && uvicorn app.main:app --reload --port 8000"

REM 等待后端启动
timeout /t 3 /nobreak >nul

REM 启动前端
echo [2/2] 启动前端服务 (Next.js on port 3000)...
start "职护前端" cmd /k "cd /d D:\code\zhihu\zhihu-frontend && npm run dev"

echo.
echo ========================================
echo   启动完成！
echo   后端: http://localhost:8000
echo   前端: http://localhost:3000
echo ========================================
echo.
pause
