@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHON=%~dp0backend\.venv\Scripts\python.exe"
set "BACKEND_DIR=%~dp0backend"
set "FRONTEND_DIR=%~dp0frontend"
set "ENV_FILE=%~dp0.env"

if not exist "%ENV_FILE%" (
    echo [错误] 未找到根目录 .env 文件。
    echo 请在项目根目录执行：
    echo   Copy-Item .env.example .env
    echo 然后编辑 .env，填入非空的 AI_API_KEY。
    exit /b 1
)

powershell -NoProfile -Command "$hasKey = Select-String -LiteralPath $env:ENV_FILE -Pattern '^\s*AI_API_KEY\s*=\s*\S' -Quiet; if ($hasKey) { exit 0 }; exit 1"
if errorlevel 1 (
    echo [错误] .env 中缺少非空 AI_API_KEY。
    echo 请编辑 .env 后重试，例如：
    echo   notepad .env
    exit /b 1
)

if not exist "%PYTHON%" (
    echo [错误] 未找到后端虚拟环境：backend\.venv
    echo 请在项目根目录执行一次：
    echo   py -3.10 -m venv backend\.venv
    echo   "%~dp0backend\.venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
    exit /b 1
)

if not exist "%BACKEND_DIR%\requirements.txt" (
    echo [错误] 缺少 backend\requirements.txt。
    exit /b 1
)

"%PYTHON%" -c "import fastapi, uvicorn, openai, dotenv"
if errorlevel 1 (
    echo [错误] 后端依赖未安装完整。
    echo 请在项目根目录执行一次：
    echo   "%~dp0backend\.venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
    exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 npm。请先安装 Node.js LTS 并重新打开终端。
    exit /b 1
)

if not exist "%FRONTEND_DIR%\node_modules" (
    echo [错误] 前端依赖尚未安装。
    echo 请在项目根目录执行一次：
    echo   cd frontend ^&^& npm install
    exit /b 1
)

set "PYTHONPATH=%ROOT%"
echo [启动] 后端：http://localhost:8000
start "Knowledge Map Backend" /D "%BACKEND_DIR%" cmd /k ""%PYTHON%" -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

echo [启动] 前端：http://localhost:5173
start "Knowledge Map Frontend" /D "%FRONTEND_DIR%" cmd /k "npm run dev"

echo.
echo 前端：http://localhost:5173
echo 后端：http://localhost:8000
echo API 文档：http://localhost:8000/docs
endlocal
