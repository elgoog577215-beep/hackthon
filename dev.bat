@echo off
REM 本地开发环境启动脚本 (Windows)
REM 前端: Vite dev server (http://localhost:5173)
REM 后端: Uvicorn with reload (http://localhost:8000)

echo 🚀 启动 Knowledge Map AI 本地开发环境...
echo.

REM 检查.env文件
if not exist .env (
    echo ⚠️  未找到.env文件，创建示例配置...
    echo MODELSCOPE_API_KEY=your_api_key_here > .env
    echo ✅ 已创建 .env 文件，请编辑并添加你的API密钥
)

if not exist backend\data mkdir backend\data

echo 📦 启动后端 (http://localhost:8000)...
cd backend
pip install -r requirements.txt -q
start "Backend" cmd /c "set PYTHONPATH=.. && uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
cd ..

echo 📦 启动前端 (http://localhost:5173)...
cd frontend
call npm install --silent
start "Frontend" cmd /c "npm run dev"
cd ..

echo.
echo ✅ 服务已启动
echo    前端: http://localhost:5173
echo    后端: http://localhost:8000
echo    API文档: http://localhost:8000/docs
echo.
echo 关闭窗口即可停止服务
pause
