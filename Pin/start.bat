@echo off
echo ========================================
echo Pin - Recruitment Data Platform
echo ========================================

echo.
echo [1/3] Starting Backend API (port 8000)...
start "Backend API" cmd /k "cd /d D:\code\python\Pin\backend\api && python main.py"

echo.
echo [2/3] Starting Crawler Service (port 8001)...
start "Crawler Service" cmd /k "cd /d D:\code\python\Pin\services && python crawler_service.py"

echo.
echo [3/3] Starting Frontend (port 3000)...
start "Frontend" cmd /k "cd /d D:\code\python\Pin\frontend && npm run dev"

:: 等待1秒，给前端启动缓冲，再打开浏览器
timeout /t 1 /nobreak >nul
echo.
echo Opening frontend page in default browser...
start http://localhost:3000

echo.
echo ========================================
echo All services started!
echo.
echo Backend API:      http://localhost:8000
echo Crawler Service:  http://localhost:8001
echo Frontend:         http://localhost:3000
echo.
echo API Docs:         http://localhost:8000/docs
echo.
echo Crawler Management: http://localhost:3000/admin/crawler
echo System Monitor:     http://localhost:3000/admin/monitor
echo ========================================
pause