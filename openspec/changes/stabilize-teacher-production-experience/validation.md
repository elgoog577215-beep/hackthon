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
- `backend/.venv/bin/python -m pytest backend/tests`：完整结束，`3927 passed / 23 failed / 3 skipped / 2 xfailed / 1 xpassed`。其中 14 项为已在纯净远端 HEAD 复现的基线，3 项为本机环境开关差异，另 6 项来自相邻 PPT V3/V5 与课程结构调整在途链；本 change 的状态投影、教师资产恢复和大纲精确任务身份测试没有失败。
- 本 change 后端高风险定向回归：`73 passed`；含跨讲结构、三仓引用迁移、journal、partial retry、CAS 撤销和教师课程主链。
- `backend/.venv/bin/python -m ruff check backend tests --select E9,F63,F7,F82`：通过。
- `npm --prefix frontend test -- --run`：`174` 个文件、`1451 passed`。
- `npm run build`：通过，`5383 modules transformed`；仅保留现有大 chunk 告警，前端包体不在本 change 范围。
- 中英文 locale JSON：解析通过。
- `stabilize-teacher-production-experience` 与 `split-teacher-lesson-authoring-v1` strict validation：通过。
- 全量 OpenSpec strict validation：`36 passed / 0 failed`。
- `git diff --check`：通过。

结论：本 change 的本地发布门已通过；全量后端的 23 项既有或相邻在途失败仍如实保留，不记为全量通过。

### 状态合同最终补验（2026-09-05）

- 后端投影、readiness 与 PPT 链路定向回归：`104 passed`。
- 前端共享适配器、工作台、离线投影和教师界面边界全量纳入上述 `1436 passed`。
- `waiting_for_input` 只调用大纲详情继续命令；`waiting_for_review` 在当前工作台只显示待审阅状态，不嵌入旧任务中心，不暴露通用继续或重新生成。
- 未知态、缺失真实 task ID、幽灵 checkpoint 和不可恢复质量阻断均只允许查看原因；可恢复质量阻断只恢复投影授权的 task ID。
- 前端生产构建、Ruff、中英文 locale JSON、当前 change 与全量 OpenSpec strict validation（`36 passed / 0 failed`）、`git diff --check` 全部通过。

### 状态、动作与任务身份二次收口（2026-09-05）

- 每个任务型写操作现在必须同时满足 `allowed_actions` 授权和 `action_targets[action]` 中存在精确 task ID；阶段动作与任务 ID 不再分别做无关系并集。mixed batch 中可重试失败与未知任务并存时，只把可重试任务放入重试目标。
- 教案、讲义批量恢复必须显式提交 `resume_job_ids`。后端在创建任何子任务前统一校验课程、资产类型、讲次、来源修订和恢复资格；空列表不猜 latest，取消任务不恢复，失败任务必须显式 `retryable=true`。
- 大纲详情继续与未确认草稿重新生成均携带投影授权的精确任务 ID；Store 和 TaskManager 不再按 course ID 查找 latest。服务端返回不同任务身份时前端拒绝继续。
- `waiting_for_input` 只授权 `provide_input`，`waiting_for_review` 只授权 `review_generation`。后端不再暴露通用暂停、取消、继续或重试；前端即使收到旧版或非法组合也会隐藏并拒绝这些通用动作。
- 未知态、缺 ID、幽灵 checkpoint、不可恢复质量阻断和结构无效的新投影全部 fail closed，只允许查看原因；仅当新投影完全不存在时才允许短期 legacy fallback。
- 针对性后端联合回归 `220 passed`，等待态、投影、教师生成与恢复联合回归 `195 passed`；前端共享适配器与工作台 `120 passed`。最终完整前端 `1451 passed`，生产构建通过；后端全量如上完整结束且本次链路无失败。

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

## 3.7 / 3.3 真实失败恢复回归修正（2026-09-05）

用户以课程 `f75a76ca-3fd5-49cb-9601-6f40a1e0211f` 的截图指出：第 2 讲讲义已经明确失败并保留 3/6 个教学块，但首屏没有“重新生成”。此前 9.5 的隔离 fixture 虽验证了按钮文案，却没有复现教师资产仓库中 `jobs` 的真实归属，也只断言按钮存在于 DOM，没有验证它位于长教学块列表之前；因此“重新生成已验收”的结论超过了证据。

真实根因有两层：

1. `read_course_production_state()` 只读取 TaskManager，遗漏 `TeacherLessonAuthoringRepository.jobs`，导致同一课程右栏根据旧 jobs 显示失败，而 `course_production_state_v1` 错误返回 `15/16 / failed=0 / idle / issues=[]`。
2. 工作台按钮仍以本地 `jobs + can_generate` 组合决定恢复，外部工具栏又排在整段讲义生成映射之后；状态能够显示失败，不等于用户在首屏能够恢复。

修复后，教师资产 jobs 与 TaskManager/PPT checkpoint 在纯投影内按稳定 task ID 合并去重；`lesson-authoring` 与课程接口返回同一投影。共享前端适配器把每个阶段统一翻译为 `generate / resume_generation / retry_generation / inspect_failure / none`，教案和讲义按钮只在整份投影缺失时回退旧 jobs。可用资产的最近失败使用受限 `regenerate_ready=true`，服务端只选择最新任务失败、暂停或取消的可用讲次，不重建其他可用内容；明确不可重试的错误只给 `inspect_failure`。

真实数据只读编译结果：讲义 `total=16 / available=15 / failed=1`，第 2 讲为 `failed / task_id=tlj-090d5bd9e1df458daee059b186d9f645 / block_id=tsb-46b37443a7bc / recovery=retry_generation`。隔离浏览器复用真实页面和讲次数据，只替换旧进程尚未热加载的投影响应；首屏得到 1 个“重新生成”按钮，位置 `x=750 / y=275 / 103×34`，“只生成本讲”为 0，未点击按钮。页面自身仍发送既有匿名 usage-events 批量上报，本轮没有课程、资产或任务写请求。

回归证据：

- 后端课程生产投影与教师讲次路由：`133 passed`；覆盖仓库 jobs 自动进入投影、重复任务去重、不可重试动作、lesson-authoring 同投影响应，以及只恢复带失败 attempt 的 last-good 讲义。
- 前端状态、工作台、讲义文档与 Store：`98 passed`；覆盖完整状态—动作矩阵、新投影与旧 jobs 冲突、新投影失败但旧 jobs 缺失、唯一批量按钮和工具栏位于长映射正文之前。
- `vue-tsc -b`、Ruff 定向检查和 `git diff --check` 通过。
- 截图：`output/playwright/teacher-production-retry-fix.png`。

本轮最终补验继续复用现有 `127.0.0.1:5173` / `127.0.0.1:8000`，未重启、暂停、取消、继续或重试任何真实课程任务。隔离 headed session `lingzhi-9-5-final` 拦截全部 POST、PATCH、PUT、DELETE；页面刷新后仍保留 `stage=script&lesson=L1-2&block=tsb-46b37443a7bc&task=tlj-090d5bd9e1df458daee059b186d9f645&issue=cpi-622c997b9a327886cd34&expandIssue=1`，第 2 讲、完整错误和唯一“重新生成”均保持可见。写请求记录只有被夹具拒绝的匿名 `/api/usage-events/batch`，没有课程、资产或任务写请求。

1280×800 下三栏实测为 `196 / 754 / 310px`，右栏 `display=grid / visibility=visible`；讲次导航 `scrollHeight=818 / clientHeight=658 / maxScroll=160`，滚到底后第 16 讲完整位于导航视口内；当前阶段背景/文字为 `rgb(238, 240, 255) / rgb(67, 56, 202)`，仍属原蓝紫体系。截图：`output/playwright/teacher-production-9.5/deeplink-refresh-final-1280.png`。

针对性回归复跑结果更新为：后端 `153 passed`；前端 6 个相关文件 `162 passed`。日历四项浏览器证据继续使用本节既有 `calendar-four-states-1280.png`；“教案可用、讲义未生成时下一步指向讲义”的精确分支由 `teacher-teaching-calendar-production-state.test.ts` 通过。补验切换第二个日历夹具时，既有 Vite 监听进程退出，因此没有把未完成的第二张日历截图记作新证据，也没有擅自重启服务。

## 状态、命令所有者与 PPT 恢复链最终补验（2026-09-05）

本轮继续沿“显示状态 → `allowed_actions` → `action_targets[action]` → 正式命令所有者 → 状态迁移”核对，补出并修复四类断链：

- TaskManager、教师资产仓库或大纲草稿读取失败不再解释成“空”；last-good 内容仍可读，但所有写动作关闭并进入 `unknown + inspect_failure`。
- `PPT checkpoint` 只保存执行进度，不拥有生命周期命令；即使快照写着 running/failed，也不得绑定 pause/cancel/retry。相同 task ID 同时出现在正式任务与 checkpoint 时，正式 TaskManager/teacher-asset job 永远优先。
- 历史 raw `active/queued` 若没有正式后端命令，owner/type 不匹配，或等待态出现在非大纲任务中，统一 fail closed；不再因为状态名看起来“活动”就伪造按钮。
- PPT 普通入口只接受 `idle|cancelled + generate` 或 `available + regenerate_from_latest_source`。失败恢复只由右栏原位“重新生成”消费 `retry_generation` 的精确 job ID，并以一次性 `resumeTaskId` 进入 PPT 工作区；Store 按该 ID 读取同一持久 job，后端再校验课程、讲次、类型、来源修订和可恢复性。上传并审阅保持独立，不受 AI 生成门禁影响。

后端还修复了三个命令端点与投影的错配：取消的 `course_import` 不再允许通用 resume；暂停的教师资产 job 取消后真实进入 cancelled 且不可恢复旧 ID；PPT resume 不再接受 cancelled、缺失 job、错误课程/讲次/类型或旧来源，也不再静默回退 checkpoint。

最终本轮定向证据：

- 后端状态投影、教师资产、导入恢复、AI 控制和 PPT V6：`242 passed`。
- 前端状态适配器、课程库、工作台、PPT 工作区、Store、课程空间和日历：`246 passed`。
- `vue-tsc -b` 与 Vite production build 通过，`5383 modules transformed`；locale JSON、Ruff、change strict validation 和 `git diff --check` 通过。
- 中文桌面隔离浏览器中，PPT last-good + 最新失败显示“内容已就绪 / 可使用 · 最近一次生成失败”，唯一“重新生成”位于右栏；普通“AI 生成”禁用，“上传并审阅”可用。只读路由记录中只有被拒绝的匿名 `/api/usage-events/batch`，没有课程、资产或任务写请求。截图：`output/playwright/teacher-production-ppt-state-audit.png`。

剩余兼容边界：旧通用节点生成的 HTTP/WebSocket skip/retry/stop/custom-instruction 仍按 `course_id` 查找活动任务，它不属于教师教案/讲义/PPT 主链，但仍是任务身份债务；在 9.1 完整发布观察和协议迁移前不冒险改动。当前 8000 仍是旧进程，数据目录存在其他课程的 running/pending/paused 教师资产 job，因此未重启后端、未点击恢复、未提交、未推送、未部署。
