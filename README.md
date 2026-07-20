---
title: Knowledge Map AI
emoji: "🧠"
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
---

# 灵知（Knowledge Map AI）

灵知是一个面向课程生成、连续学习和学习证据管理的 AI 学习系统。

## 本地开发（Windows PowerShell）

以下命令不需要激活虚拟环境，也不依赖全局 `pip` 或 `uvicorn`。在项目根目录执行：

```powershell
# 第一次安装
py -3.10 -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt

Set-Location .\frontend
npm install
Set-Location ..

# 仅首次：从安全示例创建自己的配置；不会覆盖已有 .env
Copy-Item .env.example .env
notepad .env

# 每次启动
.\dev.bat
```

启动后访问：

- 前端：<http://localhost:5173>
- 后端：<http://localhost:8000>
- API 文档：<http://localhost:8000/docs>

`dev.bat` 不会在启动时安装依赖；如果虚拟环境、Python 依赖或 `frontend\node_modules` 缺失，它会给出一次性安装命令后退出。

### PowerShell 的 Activate.ps1 报错

如果直接输入 `backend\.venv\Scripts\Activate.ps1` 后出现“无法加载模块 backend”，PowerShell 将路径当作模块/命令名解析了。相对路径需要调用运算符：

```powershell
& .\backend\.venv\Scripts\Activate.ps1
```

不过本项目推荐始终直接使用 `.\backend\.venv\Scripts\python.exe`，无需激活，也能确保使用正确的 Python 环境。

## AI 提供方配置

根目录 `.env` 只能选择一个提供方。先用 `.env.example` 创建文件，再填入自己的密钥；不要提交真实密钥。

### 官方 DeepSeek（推荐）

```dotenv
AI_API_KEY=your_deepseek_api_key
AI_API_BASE=https://api.deepseek.com
AI_THINKING_ENABLED=true
AI_SLIDE_PLANNER_ENABLED=true

# 可省略：官方 DeepSeek 会自动使用以下默认模型
AI_MODEL=deepseek-v4-pro
AI_MODEL_FAST=deepseek-v4-flash
```

官方 DeepSeek 使用 OpenAI 兼容地址 `https://api.deepseek.com`。未显式设置 `AI_MODEL*` 时，智能任务默认 `deepseek-v4-pro`，快速任务默认 `deepseek-v4-flash`；thinking 会按官方 OpenAI SDK 兼容参数发送。`AI_THINKING_ENABLED=false` 会统一关闭 thinking。为兼容旧配置，`AI_ENABLE_THINKING` 仍可使用，但新配置请使用 `AI_THINKING_ENABLED`。

### ModelScope（兼容保留）

```dotenv
AI_API_KEY=your_modelscope_api_key
AI_API_BASE=https://api-inference.modelscope.cn/v1
AI_THINKING_ENABLED=true
AI_SLIDE_PLANNER_ENABLED=true

# 可选：不设置时使用项目内置的 Qwen3.5 候选模型列表
# AI_MODEL_CANDIDATES=Qwen/Qwen3.5-27B,Qwen/Qwen3.5-122B-A10B,Qwen/Qwen3.5-397B-A17B
# AI_MODEL_FAST_CANDIDATES=Qwen/Qwen3.5-27B,Qwen/Qwen3.5-122B-A10B,Qwen/Qwen3.5-397B-A17B
```

ModelScope 路径默认只使用按稳定性排序的 Qwen3.5 候选模型，并继续发送
`enable_thinking` 兼容字段。`AI_SLIDE_PLANNER_ENABLED=true` 用于启用 AI
幻灯片规划功能。

## 技术栈

- 前端：Vue 3、Vite、TailwindCSS、Mermaid.js
- 后端：FastAPI、Python 3.10
- AI：官方 DeepSeek OpenAI 兼容接口或 ModelScope 兼容接口

更多开发说明见 [DEVELOPMENT.md](./.kiro/docs/DEVELOPMENT.md)。
