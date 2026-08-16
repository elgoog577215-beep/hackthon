# Adapter Isolation Handoff

## Integrated Boundary

- 学生端：保留 `/courses`、`/course/:courseId/learn/:nodeId?`、`/course/:courseId/ppt` 及原有能力。
- 教师端：使用 `/teacher/courses`、`/teacher/course/:courseId/*`，其中 PPT 为 `/teacher/course/:courseId/ppt`。
- 共享能力：课程生成、教案工作台、PPT 表示与生成 Store、后端引擎和课程数据仍为同一套。
- 隔离内容：教师路由、页面编排、`course_generation` 任务投影、教师预览无学习数据写入。

## Compatibility Contract

- `useTeacherCourseRuntime()` 是教师侧唯一接入边界。
- `courseStore.loadCourse()` 默认语义不变；教师仅通过可选 `taskType` 和 `includeLearningRecords: false` 增强。
- `/api/courses/{course_id}/task` 默认行为不变；教师通过可选 `task_type=course_generation` 精确读取。
- 全局任务中心保留全部任务，课程生命周期投影过滤 PPT/representation 构建任务。

## Future Integration Rule

朋友继续升级学生端或共享生成能力时，教师端自动复用兼容升级；只有路由、入参、返回结构或任务类型发生破坏性变化时，集中修改适配器和契约测试。不要复制 Store 或生成引擎。

## Deferred

- 教师发布快照如何进入学生端。
- 教师/学生身份与权限模型。
- 学生反馈和 AI 使用聚合如何回流教师端。

## Verification

见 `verification/adapter-isolation-final.md`。
