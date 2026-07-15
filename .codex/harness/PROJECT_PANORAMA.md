# 项目全景

<!-- HARNESS:INIT-CONTEXT -->

最后更新依据：Init receipt `sha256:6f816159393a7bfd5f3582006ae30be9bd432c002cdac820a6b5741662ef50f8`

## 当前快照

- Project root: `D:/xsh/cursor/灵知/hackthon`
- OpenSpec: available / builtin-spec-driven / 1.5.0
- Design: design-partial / sha256:4791e9edb49b559491d2d4bc88df7eb642b0fe0f40d16e034746ae03d6e829df
- UI classification: required

## 最近有意义变化

- 新增右上角“模型配置”：本机可保存多个 OpenAI 兼容 LLM 配置并切换；密钥仅保存在被 Git 忽略的后端数据文件中，配置接口只允许回环地址访问且从不回传密钥。

## Runtime Contract

见 `contracts/runtime-ports.json`；Init 不猜启动命令或端口。

## 系统地图

- `.dockerignore`
- `.gitattributes`
- `.github/`
- `.gitignore`
- `.impeccable.md`
- `.kiro/`
- `backend/`
- `backend-runtime.err.log`
- `backend-runtime.log`
- `design-qa.md`
- `DESIGN.md`
- `dev.bat`
- `dev.sh`
- `Dockerfile`
- `docs/`
- `frontend/`
- `frontend-runtime.err.log`
- `frontend-runtime.log`
- `LICENSE`
- `ms_deploy.json`
- `npm-install.err.log`
- `npm-install.log`
- `openspec/`
- `package-lock.json`
- `pip-install.err.log`
- `pip-install.log`
- `pyproject.toml`
- `pytest.ini`
- `README.md`
- `scripts/`
- `SESSION_MEMORY_FEATURE.md`
- `shared/`
- `tests/`

## API / UI / Data Contracts

- OpenSpec changes: `openspec/changes/`
- 项目设计真源: `DESIGN.md`（仅在用户批准后存在）
- 工具设计适配: `.impeccable.md`（从 DESIGN.md 派生）

## 近期重要变化

<!-- HARNESS:RECENT-CHANGES:START -->
- 统一 Init 已建立项目基础上下文。
<!-- HARNESS:RECENT-CHANGES:END -->

## 决策

- 全局能力留在用户级 Harness；项目只保存数据与 artifacts。
- Design Init 不自动晋升全局审美记忆。

## 已知风险

- runtime-not-started-in-light-init

## 未关闭问题

- 运行时、端口和浏览器视觉基线在实际开发任务中补齐。

## 下一次会话优先读取

- `PROJECT_PANORAMA.md`
- `SESSION_BRIEF.md`
- 当前 OpenSpec change / plan
- `DESIGN.md`（若存在）
