---
title: Knowledge Map AI
emoji: "🧠"
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
---

# 灵知（Knowledge Map AI）

灵知是一套以结构化课程为核心，连接教师课程生产、统一学习现场、学习证据驱动课程生长和同源教学表达的 AI 课程系统。

当前项目已经形成课程生成、结构化课程、正式练习、学习事实、AI 老师、课程调整和 PPT 同源表达主链，正在收束教师端课程与教案生产工作台以及长期课程生长闭环。准确状态查看[产品状态](./docs/产品状态.md)。

## 文档入口

| 想了解什么 | 文档 |
| --- | --- |
| 产品最终要设计成什么样 | [产品蓝图](./docs/产品蓝图.md) |
| 当前做到哪里、下一步是什么 | [产品状态](./docs/产品状态.md) |
| 代码仓库、领域真源和运行链怎样组织 | [系统架构](./docs/系统架构.md) |
| 教师端与学生端怎样隔离、共享哪些能力 | [教师端与学生端运行边界](./docs/教师端与学生端运行边界.md) |
| AI 开发时长期遵守哪些项目规则 | [项目规则](./AGENTS.md) |
| 当前高影响功能怎样设计和实施 | [`openspec/changes/`](./openspec/changes/) |
| 历史研究、验收和决策依据 | [`docs/研究/`](./docs/研究/)、[`docs/验收/`](./docs/验收/)、[`docs/归档/`](./docs/归档/) |

AI Agent 的正式执行规则位于 [AGENTS.md](./AGENTS.md)。它主要面向 AI，不替代本文的人类上手说明。

## 技术栈

- 前端：Vue 3、Vite、Pinia、Element Plus、Tailwind CSS、Mermaid、KaTeX。
- 后端：FastAPI、Python 3.10+。
- AI：官方 DeepSeek OpenAI 兼容接口或 ModelScope 兼容接口。
- 代码执行：独立 `runner/` 服务。
- 规格：OpenSpec。

## 本地开发

### macOS / Linux

在项目根目录执行：

```bash
# 第一次安装
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt

cd frontend
npm install
cd ..

# 仅首次创建本地配置，不覆盖已有 .env
cp -n .env.example .env

# 每次启动
./dev.sh
```

### Windows PowerShell

```powershell
# 第一次安装
py -3.10 -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
.\backend\.venv\Scripts\python.exe -m pip install -r .\backend\requirements-dev.txt

Set-Location .\frontend
npm install
Set-Location ..

# 仅首次创建本地配置
Copy-Item .env.example .env
notepad .env

# 每次启动
.\dev.bat
```

项目推荐直接调用虚拟环境中的 Python，不要求激活虚拟环境。若需要手工激活 PowerShell 环境，使用：

```powershell
& .\backend\.venv\Scripts\Activate.ps1
```

启动后访问：

- 前端：<http://localhost:5173>
- 后端：<http://localhost:8000>
- API 文档：<http://localhost:8000/docs>

`dev.sh` 和 `dev.bat` 会检查配置、依赖、端口与健康状态，但不会在每次启动时自动安装依赖。

## AI 提供方配置

从 `.env.example` 创建 `.env`，选择一个主提供方并填写自己的密钥。可以额外配置一个仅在主模型池全部失败后启用的 ModelScope 兜底。不要提交 `.env` 或真实密钥。

### 官方 DeepSeek

```dotenv
AI_API_KEY=your_deepseek_api_key
AI_API_BASE=https://api.deepseek.com
AI_THINKING_ENABLED=true
AI_SLIDE_PLANNER_ENABLED=true

# 可选；未设置时使用项目默认模型
AI_MODEL=deepseek-v4-pro
AI_MODEL_FAST=deepseek-v4-flash
```

### ModelScope

```dotenv
AI_API_KEY=your_modelscope_api_key
AI_API_BASE=https://api-inference.modelscope.cn/v1
AI_THINKING_ENABLED=true
AI_SLIDE_PLANNER_ENABLED=true

# 可选；未设置时使用项目内候选模型列表
# AI_MODEL_CANDIDATES=Qwen/Qwen3.5-122B-A10B,Qwen/Qwen3.5-397B-A17B,deepseek-ai/DeepSeek-V4-Flash
# AI_MODEL_FAST_CANDIDATES=deepseek-ai/DeepSeek-V4-Flash,Qwen/Qwen3.5-122B-A10B,Qwen/Qwen3.5-397B-A17B
```

### ModelScope 最后兜底

主提供方仍使用上面的 `AI_*` 配置；以下凭据只在主模型池因额度、限流、连接故障或提供方鉴权故障而不可用时调用：

```dotenv
MODELSCOPE_API_KEY=your_modelscope_fallback_key
MODELSCOPE_BASE_URL=https://api-inference.modelscope.cn/v1/
MODELSCOPE_MODEL=Qwen/Qwen3.5-35B-A3B
# PPT story/visual roles may use a verified cross-course route without
# changing the model order used by course generation or assessments.
AI_PPT_STORY_MODELS=deepseek-ai/DeepSeek-V4-Flash-0731,Qwen/Qwen3.5-122B-A10B
AI_PPT_VISUAL_MODELS=deepseek-ai/DeepSeek-V4-Flash-0731,Qwen/Qwen3.5-122B-A10B
```

题目生成固定使用唯一的完整质量策略，不再暴露速度或思考档位。链路保留完整候选内容、逐题独立求解、选择性模型思考和最多三轮质量修复；确定性本地解题器只处理能严格证明的合同，其余继续交给模型独立求解。历史客户端传入的 `fast` 或 `deliberate` 只作为兼容值接收，服务端会在创建或恢复任务前统一归一为 `complete`。任何带有 `ai_validation_unavailable` 的本地保底合同都会被丢弃，不能自动进入正式题库。生产部署从 GitHub Actions secret `MODELSCOPE_API_KEY` 写入服务器持久化 `.env`，发布包和浏览器端都不包含真实密钥。

## 联网检索配置

课程生成、题库和 AI 老师共用 `backend/web_retrieval.py` 检索网关。默认 Provider 是与应用同机部署、仅监听 `127.0.0.1:8080` 的 SearXNG，不需要商业搜索 API 密钥；所有用户开关仍默认关闭，PPT 链路不使用联网检索。

```dotenv
WEB_RETRIEVAL_PROVIDER=searxng
SEARXNG_BASE_URL=http://127.0.0.1:8080
SEARXNG_REQUEST_TIMEOUT_SECONDS=6
WEB_RETRIEVAL_V2_MODE=off
# WEB_RETRIEVAL_V2_USER_IDS=teacher_user_id
```

生产环境通过 GitHub Actions 的 `Provision Lingzhi SearXNG` 手动工作流首次安装或显式升级固定镜像。常规应用发布不会更新 SearXNG；当检索模式为 `allowlist` 或 `on` 时，会在停止当前应用前检查 `/config` 和一次 JSON 搜索，失败即终止发布。Exa 只保留显式兼容适配器，不会成为自动兜底。

## 测试与检查

当前两套后端测试目录存在同名 `conftest` 收集边界，需要分别运行：

```bash
backend/.venv/bin/python -m pytest backend/tests
backend/.venv/bin/python -m pytest tests
backend/.venv/bin/python -m ruff check backend tests
```

前端测试、类型检查和生产构建：

```bash
cd frontend
npm test
npm run build
```

规格和仓库卫生：

```bash
openspec validate --all
scripts/check-tracked-ignored.sh
git diff --check
```

局部改动可以先运行相关测试，但提交说明必须明确哪些完整检查没有运行。Mock、演示预设和本地保底不能代替真实模型、浏览器或生产验收。

## 仓库结构

```text
frontend/        Vue 前端与用户界面
backend/         FastAPI、领域服务、生成和学习运行时
runner/          独立代码执行服务
tests/           兼容与整链测试
scripts/         迁移、验收、部署和诊断工具
docs/            当前中文文档与按需历史材料
openspec/        正式规格和变更任务
```

详细模块、数据真源和主链查看[系统架构](./docs/系统架构.md)。

## 开发协作

- 小型修复直接修改代码并增加回归测试。
- 高影响功能、核心流程、数据库迁移和正式接口变化进入 `openspec/changes/<change>/`。
- 当前产品结论更新产品蓝图；当前进度更新产品状态；代码边界更新系统架构；重复高代价错误提炼到项目规则，并优先增加自动化测试。
- 不提交密钥、运行数据、缓存、录屏和导出文档。
- 用户可见文案同时维护中文和英文，并验证桌面、移动端与英文模式。

## 构建与部署

- Docker 入口：[Dockerfile](./Dockerfile)。
- Runner 独立部署：[docker-compose.runner.yml](./docker-compose.runner.yml)。
- 发布包构建：`scripts/build-deploy-artifact.sh`。
- 生产部署：`scripts/deploy-production.sh`。
- GitHub Actions 部署：`.github/workflows/deploy-lingzhi.yml`。
- SearXNG 手动部署：`.github/workflows/provision-searxng.yml`；固定配置位于 `deploy/searxng/`。

生产发布必须完成构建、健康检查、活动任务恢复和回滚验证；不要用一次本地启动代替生产验收。

## 许可证

查看 [LICENSE](./LICENSE)。
