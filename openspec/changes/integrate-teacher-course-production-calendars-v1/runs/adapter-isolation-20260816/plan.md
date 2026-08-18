# Adapter Isolation Run Plan

## Goal

在不削减或改写学生端现有课程生成、PPT、编辑与 AI 能力的前提下，补齐教师端适配边界：教师使用独立路由、页面编排和课程生成任务投影，底层继续复用主分支的课程生成、教案和 PPT 引擎。

## Authority

- Source turn: `user-20260816-execute-teacher-student-adapter-isolation`
- Change: `integrate-teacher-course-production-calendars-v1`
- Run: `adapter-isolation-20260816`
- Excluded: `.env`、运行数据、用户生成文件、push、破坏性清理。

## Acceptance Criteria

- AC1 学生 `/courses`、`/course/:courseId/learn/:nodeId?`、`/course/:courseId/ppt` 的路由与能力保持不变。
- AC2 教师 PPT 使用 `/teacher/course/:courseId/ppt`，返回教师生产上下文；底层仍使用现有 `PptWorkspaceView` 和 `useTeachingRepresentationsStore`。
- AC3 教师课程加载显式读取 `course_generation` 任务，不把 `slide_deck_variant_build` 或 `teaching_representation_build` 投影为课程生成状态。
- AC4 共享任务列表仍保留全部任务供任务中心使用，但课程生成状态 Map 只消费课程生成/导入任务。
- AC5 底层能力升级无需复制到教师端；适配层只提供契约、路由和状态投影，不复制课程/PPT数据。
- AC6 后端任务类型过滤、前端路由/适配层/状态投影有自动化测试；相关前端构建通过。

## Execution

- [x] E1 为课程任务查询增加向后兼容的 `task_type` 过滤。
- [x] E2 修正前端课程状态投影，避免 PPT 任务覆盖课程生成任务。
- [x] E3 扩展教师运行时适配契约，集中教师课程加载和 PPT 路由。
- [x] E4 注册教师独立 PPT 路由并接入教师生产页；学生 PPT 路由保持不变。
- [x] E5 增加后端和前端契约测试。
- [x] E6 运行定向测试、构建、diff/secret/runtime scope 检查和浏览器验证。

## Stop Rules

- 如果需要复制一套生成 Store、PPT Store 或后端引擎，停止并重新设计。
- 如果需要破坏学生 API 默认语义，改为向后兼容参数或教师端点。
- 运行数据与已有用户未提交改动不得进入本轮 source diff。
