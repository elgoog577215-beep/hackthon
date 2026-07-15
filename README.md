---
title: Knowledge Map AI
emoji: 🧠
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
---

# 灵知（KnowledgeMap）AI 学习系统

这是一个围绕课程生成、连续学习、正式学习证据、学习者模型和统一 AI 老师构建的智能学习系统。

## 功能特点
- **智能课程生成**：根据学习目标、难度和资料生成课程结构、正文与正式学习资产。
- **连续学习工作区**：保留课程目录、连续正文和统一 AI 老师，并支持断点恢复。
- **学科知识库**：用跨课程正式知识树表达学科结构，通过课程知识映射显示本课覆盖。
- **教学标准与学习者模型**：统一能力点、易错点和提升点，并从正式证据投影个人知识状态。
- **正式练习与复习**：题目、作答、诊断、补救和复验共享同一条可审计链路。

## 技术栈
- **Frontend**: Vue 3, Vite, TailwindCSS, Mermaid.js
- **Backend**: FastAPI, Python 3.10
- **AI Model**: ModelScope API (Qwen/Qwen2.5)

## 本地运行

首次运行前，在项目根目录创建 `.env` 并至少配置：

```bash
AI_API_KEY=你的模型服务密钥
AI_API_BASE=https://api-inference.modelscope.cn/v1
```

安装后端依赖到 `backend/.venv`，并在 `frontend` 执行一次 `npm install`。之后使用统一启动脚本：

```bash
# Linux/macOS
./dev.sh

# Windows
dev.bat
```

脚本会在前后端都通过健康检查后输出访问地址。需要避开已占用端口时可显式指定：

```bash
BACKEND_PORT=8011 FRONTEND_PORT=5197 ./dev.sh
```

或手动分别启动：

```bash
# 后端
cd backend
pip install -r requirements.txt
PYTHONPATH=.. uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 前端（新终端）
cd frontend
npm install
npm run dev
```

访问：
- 前端: http://localhost:5173
- 后端: http://localhost:8000
- API文档: http://localhost:8000/docs

详细开发指南请查看 [DEVELOPMENT.md](./.kiro/docs/DEVELOPMENT.md)

## 部署
本项目已配置 Dockerfile，可直接部署到 ModelScope 创空间或 Docker 环境。
