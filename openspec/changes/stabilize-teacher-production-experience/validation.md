# 验收记录

## 1.3 后端测试基线分类（2026-09-05）

当前工作树命令：

```bash
backend/.venv/bin/python -m pytest backend/tests -q
```

在题库后台重建线程长期无新进度后手动中止；中止前结果为：

```text
17 failed, 2346 passed, 2 xfailed, 1 xpassed
```

悬挂发生在 `question-bank-rebuild-loop` 后台线程，主线程等待锁，`-q` 未留下正在执行的测试节点，因此不把最后显示的失败测试冒充为悬挂来源。

### 远端 HEAD 基线失败

在隔离工作树 `2dc1a61227ae9ca661eb2b08805c7e3c54e66e07` 复现 14 项：

- `test_ai_teacher_protocol.py::test_ai_teacher_does_not_duplicate_conversation_history_in_user_prompt`
- `test_course_generation_budget.py::test_parallel_node_context_never_depends_on_generated_predecessor_body`
- `test_course_pedagogy_archetypes.py::test_v1_persisted_profile_remains_readable_without_course_migration`
- `test_cross_subject_question_generation.py` 的 5 个现有题型/语义原型断言
- `test_generation_failure_recovery.py::test_new_v6_task_records_the_current_checkpoint_contract`
- `test_material_backed_course_generation.py` 的 2 个现有蓝图/仅大纲断言
- `test_question_bank.py::test_legacy_review_queue_migrates_without_republishing_teacher_rejections`
- `test_slide_ai_runtime.py` 的 2 个现有 V5/V6 runtime 断言

主要复现命令：

```bash
/Users/yq/Desktop/灵知/hackthon/backend/.venv/bin/python -m pytest \
  backend/tests/test_ai_teacher_protocol.py \
  backend/tests/test_course_generation_budget.py \
  backend/tests/test_course_pedagogy_archetypes.py \
  backend/tests/test_cross_subject_question_generation.py \
  backend/tests/test_generation_failure_recovery.py \
  backend/tests/test_material_backed_course_generation.py \
  backend/tests/test_slide_ai_runtime.py \
  -q

/Users/yq/Desktop/灵知/hackthon/backend/.venv/bin/python -m pytest \
  backend/tests/test_question_bank.py::test_legacy_review_queue_migrates_without_republishing_teacher_rejections \
  -q
```

### 本机环境开关差异

3 项失败由本机 `.env` 的 `AI_THINKING_ENABLED`、`SLIDE_DECK_V6_ENABLED` 和 `SLIDE_DECK_V6_DEFAULT_ENABLED` 与测试预期不同引起：

- `test_assessment_generation_orchestrator.py::test_complex_generation_reserves_answer_budget_and_uses_compact_candidate`
- `test_assessment_generation_profiles.py::test_batch_generation_does_not_force_thinking_for_simple_items`
- `test_course_logic_upgrade.py::test_upgrade_course_logic_unlocks_v4_without_rewriting_document`

使用测试预期环境复核：

```bash
AI_THINKING_ENABLED=true \
SLIDE_DECK_V6_DEFAULT_ENABLED=false \
SLIDE_DECK_V6_ENABLED=false \
backend/.venv/bin/python -m pytest \
  backend/tests/test_assessment_generation_orchestrator.py::test_complex_generation_reserves_answer_budget_and_uses_compact_candidate \
  backend/tests/test_assessment_generation_profiles.py::test_batch_generation_does_not_force_thinking_for_simple_items \
  backend/tests/test_course_logic_upgrade.py::test_upgrade_course_logic_unlocks_v4_without_rewriting_document \
  -q
```

结果：`3 passed`。

### 本 change 回归

严格持久化初版曾使运行协程持有的任务/`guided_workflow` 引用失效，导致教学确认后错误跳过发布确认。修复后保留严格“先写盘、后发布内存”语义，同时维持运行对象身份；验证：

```bash
backend/.venv/bin/python -m pytest -q \
  backend/tests/test_task_manager_runtime_durability.py \
  backend/tests/test_generation_version_workflow.py::test_guided_job_requires_teaching_confirmation_before_content
```

结果：`7 passed`。

结论：已识别的失败中没有未分类的本 change 回归；全量套件仍受 14 项远端基线失败和题库后台线程悬挂影响，不能记为全量通过。

## 9.4 本地发布门

最终本地验证（2026-09-05）：

- `backend/.venv/bin/python -m pytest tests -q`：`112 passed`。
- `backend/.venv/bin/python -m pytest backend/tests -q`：中止前 `2346 passed / 17 failed`；14 项在纯净远端 HEAD 可复现，3 项为本机环境开关差异且恢复测试环境后通过，题库后台线程悬挂单独记录在 1.3；无未分类的本 change 回归。
- 本 change 后端高风险定向回归：`73 passed`；含跨讲结构、三仓引用迁移、journal、partial retry、CAS 撤销和教师课程主链。
- `backend/.venv/bin/python -m ruff check backend tests --select E9,F63,F7,F82`：通过。
- `npm test -- --run`：`172` 个文件、`1378 passed`。
- `npm run build`：通过，`5383 modules transformed`；仅保留现有大 chunk 告警，前端包体不在本 change 范围。
- 中英文 locale JSON：解析通过。
- `stabilize-teacher-production-experience` 与 `split-teacher-lesson-authoring-v1` strict validation：通过。
- 全量 OpenSpec strict validation：`36 passed / 0 failed`。
- `git diff --check`：通过。

结论：本 change 的本地发布门已通过；全量后端中的远端基线失败和题库线程悬挂仍如实保留，不记为全量通过。

## 4.7 跨讲结构操作与正式引用迁移（2026-09-05）

已用现有 CourseEvolution domain candidate executor 和 operation journal 接通三个窄仓储边界：教案/讲义、PPT representation registry、题库 immutable bundle。未新增状态机或平行执行器。

- 移动和换序保持稳定讲次 ID；合并保留 primary ID 并写入墓碑；拆分仅 primary 继承原 ID。
- 教案、讲义和 PPT 保留 last-good 正文与修订历史，只对受影响当前资产标记 `stale/rebuild_required`，不拼接、不复制正文。
- 题库以新 immutable bundle 执行显式引用重绑，保留题面、答案、solution 和 item identity，并用 current pointer CAS 应用/撤销。
- 三仓都支持崩溃后对账、partial 续办和 CAS 撤销；未知 domain 明确失败，不会被误记为已撤销。

定向命令：

```bash
backend/.venv/bin/python -m pytest -q \
  backend/tests/test_teacher_structure_operation_dag.py \
  backend/tests/test_teacher_structure_reference_rebind.py \
  backend/tests/test_course_evolution_operation_journal.py \
  backend/tests/test_teacher_course_development_plan.py \
  backend/tests/test_course_evolution.py
```

结果：`73 passed`。其中结构专项 `9 passed`，额外覆盖一个正式仓储失败后只重试失败 operation ID，以及撤销 CAS 不覆盖教师后续修改。

## 9.5 中文桌面端真实浏览器验收（2026-09-05）

在现有 `127.0.0.1:5173` Vite 页面上完成验收；监听进程工作目录为
`/Users/yq/Desktop/灵知/hackthon/frontend`。未启动、停止或替换现有服务。

为避免连接或改写真实课程与任务，使用隔离的 headed Playwright session
`lingzhi-state-ui`，以页面级 `page.route('**/api/**')` 提供三个虚拟课程：

- `fresh-course`：四阶段全新未生成；
- `running-course`：大纲生成中，稳定任务 `task-running-001`；
- `ui-course`：16 讲，教案和讲义整课均保留 `15/16` 可用结果，第 16 讲带失败 issue、`block-3`、`task-16` 和待教师核对的 AI 推荐来源。

mock 只响应验收所需的确定性只读接口；已存在的来源关系使用正式目标 ID
`lesson-plan:L1-16` 表达，避免把缺失关系误当成用户选择并触发自动保存。未知
API 一律返回 404，显式请求 `/api/__playwright_unknown_endpoint__` 得到 404；
最终各场景的请求监听均为 `writes=[]`，没有 POST、PUT、PATCH 或 DELETE。

主要命令：

```bash
PWCLI=/Users/yq/.codex/skills/playwright/scripts/playwright_cli.sh
"$PWCLI" --session lingzhi-state-ui resize 1280 800
"$PWCLI" --session lingzhi-state-ui run-code --filename /tmp/lingzhi-9-5-route-mock.js
"$PWCLI" --session lingzhi-state-ui goto \
  'http://127.0.0.1:5173/course/fresh-course/workspace/setup'
"$PWCLI" --session lingzhi-state-ui goto \
  'http://127.0.0.1:5173/course/running-course/workspace/setup'
"$PWCLI" --session lingzhi-state-ui run-code \
  --filename /tmp/lingzhi-running-refresh-check.js
"$PWCLI" --session lingzhi-state-ui goto \
  'http://127.0.0.1:5173/course/ui-course/workspace/setup?stage=lesson&lesson=L1-16&block=block-3&task=task-16&issue=lesson-plan-L1-16-task-16&expandIssue=1'
"$PWCLI" --session lingzhi-state-ui run-code \
  --filename /tmp/lingzhi-rich-layout-check.js
"$PWCLI" --session lingzhi-state-ui goto \
  'http://127.0.0.1:5173/courses?view=calendar'
```

验收结果：

| 场景 | 结果 |
| --- | --- |
| 全新课程 | 大纲、教案、讲义、PPT 均显示“未生成”，进入课程信息表单，没有伪造运行任务 |
| 生成中刷新 | 刷新前后均为 `task-running-001 / running / outline_detail_generation`；页面保持“大纲 生成中 0/1”；刷新期间写请求为 0 |
| 部分失败与 last-good | 教案、讲义保持“可使用 15/16”，第 16 讲同时显示已有教学结构和“知识骨架汇编失败”，没有用最新失败覆盖整课可用结果 |
| 重新生成 | 原批量按钮显示“重新生成”，页面只有 1 个该按钮；“只生成本讲”按钮数量为 0 |
| 问题深链 | URL 保留 `lesson=L1-16&block=block-3&task=task-16&issue=lesson-plan-L1-16-task-16&expandIssue=1`；选中第 16 讲并显示“边界案例辨析”和完整失败摘要；导航写请求为 0 |
| 来源待核对 | 右栏显示“AI 推荐（待教师确认）：人工智能案例资料库.pdf”，不阻断已有教学结构 |
| 1280px 布局 | viewport 为 `1280×800`；工作台三列为 `196 / 754 / 310px`，左阶段栏 196px、讲次目录 212px、右栏 310px 且常驻；这是现有 `>1050px` 与 `<=1320px` CSS 规则的实际值 |
| 长讲次目录 | 导航 `scrollHeight=818`、`clientHeight=658`，可独立滚动；滚到底后 `scrollTop=160.5`，第 16 讲完整可见 |
| 教学日历 | 选中第 16 讲后，右栏四项为“大纲关联 / 已关联”“教案 / 生成失败”“讲义 / 未生成”“PPT / 未生成”；点击期间写请求为 0 |

截图：

- `output/playwright/teacher-production-9.5/fresh-1280.png`
- `output/playwright/teacher-production-9.5/running-refresh-1280.png`
- `output/playwright/teacher-production-9.5/last-good-deeplink-1280.png`
- `output/playwright/teacher-production-9.5/calendar-four-states-1280.png`

四张截图已目视复核：双侧栏、长讲次导航、右侧资料栏和现有蓝紫视觉/装饰样式均保留。
本轮没有修改前端依赖或 lockfile，也没有生成新的包体来源；包体构建结果仍由 9.4 单独记录。

## 3.9 失败信息职责分层（2026-09-05）

经用户结合 9.5 截图确认，只处理失败信息去重与职责分层，不改变大纲完整度字号、紧凑按钮尺寸、三栏宽度或蓝紫视觉：

- 顶部由具体错误改为课程级数量摘要：“本课程有 1 项内容生成失败，已定位到当前对象”；
- 正文对象旁只显示“本讲教案生成失败”，原位“重新生成”保持不变；
- 右栏保留完整失败原因和恢复说明，长文本自然换行，不再依赖截断；
- “知识骨架汇编失败”这条具体错误在页面只出现一次。

验收：

- `teacher-course-workbench-streaming.test.ts` 定向 `56 passed`，新增深链三层职责、具体错误单次出现和原位恢复断言；
- 前端全量 `172 files / 1379 passed`；
- `vue-tsc -b` 与 Vite 生产构建通过；
- 中英文 locale JSON 解析、OpenSpec strict 和 `git diff --check` 通过；
- `1280×800` 中文桌面隔离浏览器中，左侧阶段栏、讲次目录、正文和右栏保持原布局，右栏完整原因成功换行；浏览器未发出课程、任务或资产写请求，仅有既有匿名使用量批量上报被只读 fixture 拒绝。

截图：`output/playwright/teacher-production-ui9/failure-hierarchy-1280.png`。
