# 项目 Harness

这是项目本地的 Codex Super Harness 目录。

用途：保存上下文、验证证据、runtime contract、决策、失败教训、可复用模式和 knowledge-base 条目。

前端 / UI 项目基线：

- 新建 frontend、fullstack、game、UI demo、design dogfood 项目时，默认安装 `@playwright/test`，并生成 `playwright.config.*`、最小 smoke test 和截图 / visual proof。
- backend、CLI、library、docs-only 项目不预装 Playwright。
- 既有 UI 项目缺少 `@playwright/test` 时，优先补齐项目依赖；若本轮不能改依赖，才用临时包或普通 `npx playwright` 降级，并在 proof-pack 写清限制。

日常使用：

- 小任务：直接执行 + 轻量验证。
- 标准任务：计划 -> 执行 -> 验证 -> 沉淀。
- 高风险任务：spec / 核心文档 -> 多视角审查 -> 带护栏执行 -> 完整 proof-pack。

推荐入口：

```text
/探索 /头脑风暴 /计划 /执行 /验证 /沉淀 /研究 /审计
```

全局映射见：

```text
C:\Users\xsh\.codex\harness\commands-map.md
```

每次任务结束时，如果项目级理解发生变化，请更新：

- `PROJECT_PANORAMA.md`
- `SESSION_BRIEF.md`
- 必要的 decisions / failures / patterns / knowledge-base
