#!/bin/bash

# 本地开发环境启动脚本
# 前端: Vite dev server (http://localhost:5173)
# 后端: Uvicorn with reload (http://localhost:8000)

set -e

echo "🚀 启动 Knowledge Map AI 本地开发环境..."
echo ""

# 检查.env文件
if [ ! -f .env ]; then
    echo "⚠️  未找到.env文件，创建示例配置..."
    cat > .env << EOF
MODELSCOPE_API_KEY=your_api_key_here
EOF
    echo "✅ 已创建 .env 文件，请编辑并添加你的API密钥"
fi

mkdir -p backend/data

# 启动后端
echo "📦 启动后端 (http://localhost:8000)..."
cd backend
pip install -r requirements.txt -q
PYTHONPATH=.. uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd ..

# 启动前端
echo "📦 启动前端 (http://localhost:5173)..."
cd frontend
npm install --silent
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "✅ 服务已启动"
echo "   前端: http://localhost:5173"
echo "   后端: http://localhost:8000"
echo "   API文档: http://localhost:8000/docs"
echo ""
echo "按 Ctrl+C 停止所有服务"

# 捕获退出信号，清理子进程
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
