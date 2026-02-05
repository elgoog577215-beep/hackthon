@echo off
echo ==========================================
echo       KnowledgeMap AI - 启动脚本
echo ==========================================

echo [1/2] 正在启动后端服务 (Backend)...
start "KnowledgeMap Backend" cmd /k "cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000"

echo 等待后端初始化...
timeout /t 3 /nobreak >nul

echo [2/2] 正在启动前端服务 (Frontend)...
start "KnowledgeMap Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo ==========================================
echo             服务已启动!
echo ==========================================
echo 前端访问地址: http://localhost:5173
echo 后端API地址: http://localhost:8000
echo.
echo 请不要关闭弹出的两个命令行窗口。
echo 如果想停止服务，直接关闭窗口即可。
echo.
pause
