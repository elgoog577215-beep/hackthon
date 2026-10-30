---
title: Knowledge Map AI
emoji: "🧠"
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
---

# 灵知（Knowledge Map AI）

灵知是[启智统一仓库](../../README.md)中的课程子应用，源码位于 `apps/lingzhi`。本文件的安装、测试和脚本命令均从此应用目录执行；服务器分流见[发布说明](../../deploy/README.md)。

灵知面向学生成长，可以基于自主创建、导入或教师授权的课程独立使用，围绕同源教学内容形成个人学习路径与生成式复习、补充理解和应用材料；未来与启智的有界自适应教辅教材配合。当前应用也承载完整教师课程工作台，两端继续共用适用的课程创建、导入、正文、题目、AI 和恢复能力。

两产品分工及启智“1＋3”由[产品蓝图](docs/产品蓝图.md)统一定义。当前教师课程主链为“大纲 → 教案 → 师生共用讲义 → PPT”。学生个人讲义已接通本人资料、应试/整体理解生成、保存重开、笔记和绑定当前章节/选段的私人 AI 对话；正文及回复共用教学图解。教师授权课程库、正式练习与错题再练、基于已存事实的继续学习路径已接入代码；本地联调和生产验收状态见[产品状态](docs/产品状态.md)。

## 文档入口

- [产品蓝图](docs/产品蓝图.md)：要建设的产品、共享边界及业务设计。每项业务把内容、逻辑、交互、技术写在一起。
- [产品状态](docs/产品状态.md)：实现与蓝图的差距及验证依据。
- [AGENTS.md](AGENTS.md)：团队与 AI 工具共同遵守的项目约束。
- [项目文档](docs/README.md)：教学模板、开发参考与评测样例。

## 技术栈

- 前端：Vue 3、Vite、Pinia、Element Plus、Tailwind CSS、Mermaid、KaTeX。
- 后端：FastAPI、Python 3.11+。
- AI：浙大自建 OpenAI 兼容接口，文本模型固定为 `qwen3.8-27b`。
- 代码执行：独立 `runner/` 服务。

## 本地开发

本机 UI 验收可同时启动独立教师端与学生端，直接进入，无需注册或输入密码。先完成下文依赖安装并配置已有模型权限，再从本应用目录执行：

```bash
backend/.venv/bin/python scripts/run_ui_development.py --state-dir "$HOME/.lingzhi-development/ui"
```

教师端为 `http://127.0.0.1:5173/courses`，学生端为 `http://127.0.0.1:5174/study`；API 分别使用 8000、8001。数据与私有日志保存在指定仓库外目录，两端独立。脚本遇占用端口会退出，不停止已有服务；Ctrl+C 关闭本次启动的服务。开发身份仅在显式开发模式和本机回环请求下生效，学生身份为 `local-student:development`，可用于教师授权；不会创建密码账号，也不改变生产鉴权。脚本仅在子进程中屏蔽已停用的外部文本兜底配置，不修改 `.env`。

学生个人讲义入口为 `/study`，页头可通过“学生端”切换进入。本地实验在启动后端前显式设置 `LINGZHI_LOCAL_STUDY_AUTH=true`，即可在页面创建或登录本地学生账号；账号、原始资料、讲义和笔记保存在配置的数据目录，不提交 Git。配置启智鉴权后使用统一登录，本地注册关闭。两端共享 Qwen 与讲义写作能力；个人资料不写入教师课程。支持上传/粘贴本人资料，也可从“教师授权课程”选择已获授权讲义，冻结其修订后生成个人复习材料。正式学习使用学生会话，教师预览仍只供临时试看。运行恢复实验时使用独立数据目录和端口，保护正在使用的教师课程。

师生首页及课程页共用页头中的“教师端 / 学生端”切换，同实例分别进入 `/courses` 与 `/study`。师生前后端独立运行时，为教师前端设置 `VITE_STUDY_APP_URL` 指向学生前端的公开 `/study` 入口，为学生前端设置 `VITE_TEACHER_APP_URL` 指向教师前端的公开 `/courses` 入口，不能填写后端 API 地址；本地双端开发脚本自动配置这两个地址。独立学生构建未配置教师入口时不展示无法到达的切换。切换只决定导航，不改变账号、授权或数据目录，也不会取消后台生成任务。新建课程按目标、安排和资料起点三步保存，工作台共用课程设置与讲次；页面地址保留当前阶段及讲次，发布、授权与反馈由同一交付面板组织。

### 灵知师生服务互通

教师服务与学生服务可以保留各自的数据目录，通过发布版本与反馈回执连接；这是两个灵知实例之间的协议，不改动启智应用或混用其数据库。同实例课程授权仍可使用。跨实例运行不复制账号或课程文件，学生服务只缓存不可编辑的公开阅读表示，教师正文仍只有原仓储写入。

两端在各自启动环境中设置 `.env.example` 的五个 `LINGZHI_EXCHANGE_*` 字段：教师 `ROLE=teacher`、学生 `ROLE=student`；`NODE_ID` 是本端稳定 ID，`PEER_ID` 是对端 ID，两者互相对应；`PEER_URL` 指向对端后端根地址；`TOKEN` 是维护者私下分发的同一个至少 32 字符服务凭据。只允许 HTTPS 或本地回环 HTTP，服务凭据不进入浏览器、源码、公开日志或 Git。空值默认关闭互通，不改变现有运行目录。

1. 学生在学生服务注册/登录，教师在“学生授权”填写稳定学生 ID。本地实验也可填写对端已注册的用户名，教师服务只查询 ID，不接收账号文件、密码或会话。
2. 教师在“发布与学生反馈”发布当前可读讲义、公开题面和已采用知识关系。发布版本冻结，草稿及后续修改不自动进入学生内容；答案、量规和隐藏测试仍在发布方，正式作答由发布方按冻结题目批改。
3. 可明确勾选已确认、来源仍匹配且只引用公开讲义的 PPT 成品。公开副本删除演讲者备注、批注和作者元数据，绑定发布版本及内容校验值；旧版本成品不被后续渲染覆盖。
4. 学生刷新“教师授权课程”后进入正式学习，也可生成个人复习材料。新版本显示提示，由学生主动采用；旧版本、笔记和原作答保留。撤销/停止发布后新读取及派生操作被拒绝，不能通过缓存绕过；对端不可达时读取失败并保留原数据。
5. 正式作答的批改回执及学生主动发送的课程问题供教师查看和回复；私人讲义、笔记和私人 AI 对话不发送。教师回执不变成第二份学习事实。反馈断线保存在学生发送箱，主动重试沿同一 ID 去重；学生刷新可查看教师回复。

协议回归：从本目录运行 `python -m pytest backend/tests/test_course_exchange.py backend/tests/test_course_exchange_ppt.py`。测试使用两个合成数据目录和真实回环 HTTP；它不代表现有运行服务已经重载、浏览器整体验收或生产接通。切换运行配置前检查活动任务，并按仓库发布说明保护持久数据。

### macOS / Linux

先从仓库根目录执行 `cd apps/lingzhi`，再执行：

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

生成或批改代码实现题还需要独立的 [Runner](runner/README.md)：启动 Docker 引擎和 Runner，预拉取其 Python / JavaScript 镜像，并向应用与 Runner 注入匹配的 `FORMAL_RUNNER_URL`、`FORMAL_RUNNER_TOKEN`。普通前后端启动不会自动启动 Runner。服务缺失时，代码题停止并保留已有题库，不通过反复调用模型尝试修复基础设施。

macOS / Linux 的 `dev.sh` 与生产环境使用同一套 HTTP 文本路由政策：
所有真实模型调用都读取 `.env` 中的浙大自建 `qwen3.8-27b` 配置；
大纲、教案、讲义、页面内容稿和 PPT 仍由后端既有阶段、确认状态与质量门负责。

## AI 提供方配置

灵知的课程生成、AI 老师、内容修改、评估和 PPT 文本规划只允许调用浙大自建 `qwen3.8-27b`。团队成员向项目维护者取得授权端点与凭据，再配置 `ZJU_QWEN_BASE_URL` 和 `ZJU_QWEN_API_KEY`。真实地址和凭据只写入本地 `.env` 或部署环境 / GitHub Secrets，不进入 Git；没有模型权限时可运行不依赖模型的检查，真实调用验收须在授权环境完成。

```bash
# 在授权环境中载入 ZJU_QWEN_BASE_URL / ZJU_QWEN_API_KEY 后，
# 通过标准输入原子更新配置；脚本不会输出地址和凭据。
python3 -c 'import json,os; print(json.dumps({"api_key":os.environ["ZJU_QWEN_API_KEY"],"base_url":os.environ["ZJU_QWEN_BASE_URL"],"model":"qwen3.8-27b"}))' \
  | python3 scripts/configure_zju_qwen_provider.py --env-file .env

# 验证通用文本、PPT 故事和 PPT 视觉三个真实调用角色。
set -a; . ./.env; set +a
backend/.venv/bin/python scripts/probe_zju_qwen_runtime.py
```

本机无法直达模型端点、而已授权服务器可以访问时，可通过 SSH 建立仅监听本机的模型连接：

```powershell
python scripts/connect_qwen_via_ssh.py --config <本机私有连接配置.json>
```

辅助脚本需要 `paramiko`，连接配置包含 `ssh_host`、`ssh_user`、`target_host`、`target_port` 和 `local_port`，目标必须是现有获授权的千问服务。SSH 密码在启动时无回显输入，只留在进程内；配置文件不得含密码或模型密钥。脚本核验已有 SSH 主机密钥、保持连接，并只绑定 `127.0.0.1`。连接配置留在仓库外，服务器和凭据不写进文档。重启电脑后需要重新启动连接进程。

连接可用后，私有 `.env` 中的 `ZJU_QWEN_BASE_URL`、`AI_API_BASE`、`AI_PPT_API_BASE` 必须同时指向本机连接的 `/v1`，例如 `http://127.0.0.1:本机端口/v1`；模型及密钥仍沿用原千问配置。更新前备份 `.env`，只在本地任务空闲时重载后台。只查到模型列表不能代替真实生成、笔记保存与检查结果的验收。

运行时会检查 `AI_API_BASE`、`AI_PPT_API_BASE` 与 `ZJU_QWEN_BASE_URL` 指向同一个 `/v1` 端点，并要求所有文本模型字段都精确等于 `qwen3.8-27b`。配置不一致或模型不可用时，系统进入现有可恢复失败，不得切换到魔搭、DeepSeek 或其他文本提供方。赛事作品中的魔搭展示链接和独立图像生成不属于文本模型路由。

题目生成固定使用唯一的完整质量策略，不再暴露速度或思考档位。链路保留完整候选内容、逐题独立求解、选择性模型思考和最多三轮质量修复；确定性本地解题器只处理能严格证明的合同，其余继续交给模型独立求解。历史客户端传入的 `fast` 或 `deliberate` 只作为兼容值接收，服务端会在创建或恢复任务前统一归一为 `complete`。任何带有 `ai_validation_unavailable` 的本地保底合同都会被丢弃，不能自动进入正式题库。服务器中的模型密钥和端点只保存在目标环境私有配置，发布包和浏览器端都不包含真实密钥。

### 授权的本地 Qwen 讲义实验

需要在本机对照讲义效果时，使用隔离入口 `scripts/handout_local_experiment.py`。本地服务须提供 OpenAI 兼容 `/v1` 接口，模型别名为 `qwen3.8-27b`；脚本只接受回环地址，不修改应用 `.env` 或正式课程数据。生产环境继续使用上文规定的浙大端点。若本地服务需要认证，通过 `LINGZHI_LOCAL_API_KEY` 环境变量注入。

从本应用目录执行，替换端口和仓库外输出目录：

```powershell
.\backend\.venv\Scripts\python.exe scripts\handout_local_experiment.py --base-url http://127.0.0.1:8012/v1 --output E:\lingzhi-local-experiments\my-first-handout
```

默认输入是自编的微积分实验资料；传入 `--input input.json` 可复用冻结的课程标题、讲次、小节、教案、来源片段和要求。输出保存输入、完整提示词及指纹、真实请求计数、耗时、讲义 Markdown 和带类型块的 `handout.json`；失败保留 `partial.md`，不自动重跑。输出目录必须位于仓库外，且为空。

启动前端后打开 `/dev/handout-preview.html`，载入 `handout.json`，切换阅读/教师视图及中英文检查实际组件。页面按参考项目的侧栏、宋体正文和五色重点框呈现，支持目录跳转、批量展开解答及打印；正式讲义组件使用同一阅读样式与操作。预览仅在当前浏览器会话保留已载入 JSON，刷新后仍可继续查看。此入口只在 Vite 开发环境使用，不进入生产构建；不保存正式课程或学习记录。结构通过与公式渲染成功不代表教学内容正确，实验应另行核对来源、推导、最终答案和代表性学科样本。

`/dev/teaching-diagram-preview.html` 使用正式 Markdown/教学图表组件显示上游 44 型及二维向量、矩阵步骤扩展样例，可切换讲义与 AI 侧栏、中英文及流式未完成状态，也可粘贴隔离模型实验的 Markdown 检查。类型合同统一在 `shared/teaching-diagrams-v1.json`；讲义与师生 AI 回答在原模型请求中按内容选择图表，支持图注、来源、完整数据、放大和 SVG 下载。开发检查页不进入生产构建，图表错误只降级显示，不追加模型调用。具体证据和限制见[教学图表接入验收](docs/验收/教学图表接入验收.md)。

`/dev/teaching-interaction-preview.html` 以公开自编数据和正式助手/Markdown 组件检查阅读交互：历史恢复、引用提问、当前章切换、等待时编辑下一问题、晚绘制图表的滚动跟随、切到笔记再回来及中英文。回复仅在该开发页面模拟，不访问模型、正式 API 或课程；用于验证 UI 行为，不替代下述真实接口实验。

图型预览不验证后台接口。需要检查讲义和 AI 的真实连通性时，从本应用目录运行：

```powershell
.\backend\.venv\Scripts\python.exe scripts/teaching_api_connectivity.py --model-base-url http://127.0.0.1:8012/v1 --output E:/lingzhi-local-experiments/my-api-connectivity
```

使用已经运行、明确选择的本机 `qwen3.8-27b` 服务别名和新的仓库外空目录。脚本创建两个独立端口的临时前后端进程，以公开自编资料测试真实 HTTP、Vite 代理、SSE 与 WebSocket；覆盖登录、上传/解析/下载、师生讲义任务及回读、笔记与导出、AI 提问/历史、重复请求、来源修订冲突和权限拒绝。教师测试使用在隔离目录预置的大纲与正文，手动保存教案后发起真实讲义生成；不把夹具初始化算作大纲生成接口验收。退出仅关闭本次启动的进程，保留 `report.json`、结果与诊断日志，不修改 `.env` 或运行中的课程。此实验不替代启智正式身份、学校访问通道与生产验收，模型内容正确性及图形排版仍需分别检查。

讲义字体 `frontend/public/fonts/handout/SourceHanSerifCN-Subset.woff2` 来自参考项目的概统字体目录，原文件按 SIL OFL 1.1 分发，许可全文见同目录 `SourceHanSerif-LICENSE.txt`。字体按需加载，无第三方字体请求；子集之外的字符使用系统宋体。

概念图复用冻结教案里的 `knowledge_structure` 与 `knowledge_relations`，展示六类关系及原有条件、理由、推导和来源引用。实验 JSON 同时保存 `plan_sections`；默认自编导数样例提供六个概念和六条关系，用于检查跳转和关系显示。关系是实验输入，不能据此宣称模型自动发现了这些关系。正式教师/课程阅读组件消费已有课程知识结构，不额外调用模型或写入一套图谱；缺关系或缺正文定位时如实显示。

## 联网检索配置

课程联网来源当前冻结；以下只说明保留配置，不表示可以启用课程检索。恢复、扩展或删除需明确授权。课程生成、题库和 AI 老师的既有实现共用 `backend/web_retrieval.py` 检索网关。默认 Provider 是与应用同机部署、仅监听 `127.0.0.1:8080` 的 SearXNG，不需要商业搜索 API 密钥；所有用户开关仍默认关闭，PPT 链路不使用联网检索。

```dotenv
WEB_RETRIEVAL_PROVIDER=searxng
SEARXNG_BASE_URL=http://127.0.0.1:8080
SEARXNG_REQUEST_TIMEOUT_SECONDS=6
WEB_RETRIEVAL_V2_MODE=off
# WEB_RETRIEVAL_V2_USER_IDS=teacher_user_id
```

生产环境通过 GitHub Actions 的 `Provision Lingzhi SearXNG` 手动工作流首次安装或显式升级固定镜像。常规应用发布不会更新 SearXNG；当检索模式为 `allowlist` 或 `on` 时，会在停止当前应用前检查 `/config` 和一次 JSON 搜索，失败即终止发布。Exa 只保留显式兼容适配器，不会成为自动兜底。

## 产品使用记录

前端默认把浏览器会话、最终页面 route、Axios 写操作成功/失败和分类客户端错误写入自托管 `UsageEvent`。事件只保存稳定标识、脱敏 API 模板、状态码和耗时；不保存请求体、响应体、课程正文、答案、Prompt、错误消息、URL 查询、IP 或 User-Agent。采集失败不会改变正式业务请求结果。

```dotenv
# 服务端：默认保留 180 天、最近 200000 条。
LINGZHI_USAGE_TRACKING_ENABLED=true
LINGZHI_USAGE_RETENTION_DAYS=180
LINGZHI_USAGE_MAX_RECORDS=200000

# 可选。未配置时全局聚合端点保持关闭；不要把真实值提交到 Git。
# LINGZHI_ANALYTICS_ADMIN_TOKEN=replace-with-a-secret

# 前端构建时可完全关闭采集。
VITE_USAGE_TRACKING_ENABLED=true
```

稳定身份可以通过 `/api/usage-events/summary`、`/export` 和 `/delete` 查询、导出或硬删除自己的记录。`/api/usage-events/admin/summary` 只在配置管理密钥且请求携带 `X-Analytics-Admin-Token` 时返回跨用户聚合，不提供跨用户原始事件。

## 测试与检查

教师课程入口使用 `TeacherTeachingCalendarView`、`TeacherCourseLibraryView` 和 `TeacherCourseWorkbench`；正式学习与教师试读共用 `LearnerCourseView`。已替代的旧课程库、独立试读页和旧进度界面不再保留平行实现。教学图表由正式 Markdown 与教学图表组件渲染；冻结的联网检索代码继续按既有边界保留。

当前两套后端测试目录存在同名 `conftest` 收集边界，需要分别运行：

```bash
backend/.venv/bin/python -m pytest backend/tests
backend/.venv/bin/python -m pytest tests
backend/.venv/bin/python -m ruff check backend tests --select E9,F63,F7,F82
```

前端测试、类型检查和生产构建：

```bash
cd frontend
npm test
npm run build
```

仓库卫生：

```bash
../../scripts/check-tracked-ignored.sh
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
```

产品目标、共享边界及业务设计从[产品蓝图](docs/产品蓝图.md)进入；代码与测试体现实现，[产品状态](docs/产品状态.md)记录差距。

## 开发协作

- 按相关业务设计完成修改，根据实际影响运行必要验证。
- 高影响功能、核心流程、数据库迁移和正式接口变化先明确设计与验收边界；已确认结论写回对应设计文档，实现与设计的差距写入产品状态。
- 已确认设计写回同一业务正文，共享机制更新蓝图；实现与验收差距更新产品状态。不自动追加事实日志、经验或项目规则。
- 不提交密钥、运行数据、缓存、现场录屏和日常生成的导出文件；已检查隐私与授权、明确适用范围的固定评测样例放在 `docs/评测/`。
- 用户可见文案同时维护中文和英文，验证中文桌面及对应英文；移动端按项目规则，在明确需求后另行验证。

## 构建与部署

### 服务器与发布关系

灵知和启智当前涉及四类服务器。本文只记录服务器职责、系统关系和凭据保存位置；真实 IP、登录账号、密码、私钥、Token 和模型密钥只保存在本机密码管理器、私有 SSH 配置、GitHub / GitLab Secrets 或服务器 `.env`，不得提交到 Git。

| 文档别名 | 服务器职责 | 与灵知、启智的关系 | 访问与凭据 |
| --- | --- | --- | --- |
| `tuotu` | 拓途服务器，用户个人所有 | 只部署本仓库的灵知应用，入口为 `https://tuotuzju.com/lingzhi/`；拓途主站独立运行 | SSH 信息保存在本机私有配置；自动发布凭据保存在 GitHub Secrets |
| `zju-dev` | 浙大开发服务器，由学校提供 | 后续预计较少使用，保留开发与历史联调用途，不纳入默认正式发布链 | 访问条件与凭据由项目维护者按权限提供 |
| `zju` | 浙大正式服务器 | 承载启智主站及灵知课程子应用，发布使用本仓库经过验收的 `main` 提交 | 先通过浙江大学 aTrust / IDC 访问学校内网；凭据与运行密钥保留在私有配置 |
| `qwen` | 千问服务器 | 为启智与灵知提供模型推理服务，不随应用代码发布而重新部署模型 | 地址与凭据由维护者按权限提供，保存在调用方私有环境中 |

```text
统一仓库 main
├── 灵知应用 ────────────────────▶ tuotu（已有自动发布配置）
└── 启智平台 + 灵知课程子应用 ────▶ zju（自动发布待接通）

两处应用 ──调用模型──▶ qwen
zju-dev：保留开发环境，不作为正式发布的必经步骤
```

服务器地址、账号或密钥发生变化时，先更新私有凭据记录；只有服务器职责、发布关系或访问方式变化时才修改 README。启智联合构建、配置与发布步骤见[接入与部署说明](../qizhi/docs/灵知新版课程接入与部署.md)。目前 `tuotu` 已有 GitHub Actions 自动发布配置，`zju` 已有自动检查和源码发布包，服务器激活待接通，不能把代码推送成功当作学校站点发布成功。

- Docker 入口：[Dockerfile](./Dockerfile)。
- Runner 独立部署：[docker-compose.runner.yml](./docker-compose.runner.yml)。
- 发布包构建：`scripts/build-deploy-artifact.sh`。
- 生产入口：<https://tuotuzju.com/lingzhi/>。
- 自动发布：普通代码推送 `main` 后（`[no deploy]` 跳过发布），由仓库根目录 `.github/workflows/deploy-lingzhi.yml` 构建发布包，并通过 SSH 发布到拓途服务器的 `/opt/lingzhi`。
- 运行隔离：应用使用 `lingzhi.service` 和回环端口 `127.0.0.1:7862`，Caddy 只把 `/lingzhi/*` 转发给它；持久数据位于 `/opt/lingzhi/state`，不与拓途主站共用数据或 API。
- SearXNG 手动部署：`.github/workflows/provision-searxng.yml`；固定配置位于 `deploy/searxng/`。

服务器地址和凭据只保存在本机私有配置或 GitHub Actions secrets，不进入 Git。生产发布必须完成构建、健康检查、活动任务恢复、公开 `/lingzhi/` 路由和回滚验证；不要用一次本地启动代替生产验收。

## 许可证

查看 [LICENSE](../../LICENSE)。
