# Adapter Isolation Verification

## Verdict

PASS。教师端已经通过独立路由、运行时适配器和任务投影复用现有课程/PPT能力；学生端原路由和生成能力未被替换或削减。

## AC Evidence

- AC1：`/course/:courseId/learn/:nodeId?` 与 `/course/:courseId/ppt` 保持原路由。真实浏览器打开学生 PPT，仍显示完整生成模式、主题、联网图片与生成操作。
- AC2：教师 PPT 使用 `/teacher/course/:courseId/ppt`，继续复用 `PptWorkspaceView` 与 `useTeachingRepresentationsStore`；返回动作回到教师生产页。
- AC3：教师总览、生产和文件页统一经 `loadTeacherCourse()` 请求 `task?task_type=course_generation`，不再把 PPT 构建任务当课程生成状态。
- AC4：共享 `/api/tasks?limit=100` 仍保存全部任务；课程生命周期 Map 仅消费课程生成、课程导入和兼容旧任务。
- AC5：没有复制生成 Store、PPT Store、后端生成引擎或课程数据；适配层仅定义教师加载和路由契约。
- AC6：后端测试、前端定向测试、生产构建、浏览器行为与 diff 检查均通过。

## Commands

- `python -m pytest backend/tests/test_teacher_authoring_confirm.py backend/tests/test_generation_failure_recovery.py -q`：33 passed。
- `npm.cmd test -- src/__tests__/stores/generation-surface-isolation.test.ts src/__tests__/stores/generation-lifecycle.test.ts src/__tests__/router-learning-entry.test.ts src/__tests__/teacher-surface-boundary.test.ts`：43 passed。
- `npm.cmd test -- src/__tests__/components/ppt-workspace-view.test.ts`：18 passed。
- `npm.cmd run build`：PASS；仅保留既有 Browserslist 数据过期和大 chunk 警告。
- `git diff --check`：PASS；仅换行符提示。

## Browser Evidence

- 教师生产页：`output/playwright/adapter-isolation-20260816-final/teacher-production.png`
- 教师共享 PPT 能力：`output/playwright/adapter-isolation-20260816-final/teacher-ppt-shared-capability.png`
- 学生原 PPT 能力：`output/playwright/adapter-isolation-20260816-final/student-ppt-original-capability.png`
- 教师总览 PPT 状态一致：`output/playwright/adapter-isolation-20260816-final/teacher-overview-ppt-consistent.png`
- 教师只读预览：`output/playwright/adapter-isolation-20260816-final/teacher-preview-readonly.png`

教师预览 URL 带 `teacherPreview=1` 和 `returnTo`。本轮网络观察只有 GET，没有 `learning-records` 或 `ai-teacher/conversations` 写请求；控制台 0 error / 0 warning。

## Feedback Adjustments

- 用户明确要求“学生端能力不要被削减”：从角色功能裁剪改为路由、编排和状态隔离，生成引擎继续共享。
- 浏览器暴露任务轮询 429：增加并发合并、不可见页面暂停和 Retry-After 退避，不改变任务接口数据。
- 教师总览仍显示“必须先发布才能做 PPT”：改为基于已确认教案和真实课件表示状态，和生产页一致。

## Scope Review

未纳入 `backend/data/learning_events.json`、教学日历运行数据、教师文件空间数据、Playwright 输出、测试输出和其他既有未跟踪文件。未修改 `.env`、学生路由默认语义、生成/PPT引擎或发布关系。

## Known Gaps

- 教师发布与学生消费关系仍按用户要求后置，本轮只完成能力和状态隔离。
- 学生新标签直接打开 PPT 时课程标题可能先显示兜底标题，这是既有状态初始化行为，不属于本轮适配回归。
- Playwright CLI 的多个 page 在当前宿主都可能报告 `visible`；隐藏标签暂停已由单元测试覆盖，真实双标签轮询未出现 429。

## Learning Signal

`choice-required`：双端产品应隔离路由、编排和状态投影，而不是复制共享能力或削减其中一端功能。建议沉淀为项目经验。
