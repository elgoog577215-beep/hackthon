## Why

当前课程生成后端存在两条链路：`/api/generate_course` 使用旧 `AIService/AICourseService` 生成大纲，后台自动生成任务使用新 `CourseService` 生成正文。这样会让课程蓝图字段、上下文账本和依赖调度无法稳定贯通，导致“看起来有新能力，真实入口却没有完全吃到新能力”。

本次目标是把课程生成主链路整理成一条小而美的路径：一个课程服务负责大纲、节点契约、子节点和正文生成；旧 `AIService` 暂时保留给 quiz、图谱、学习路径、画像等非课程生成主链路能力。

## What Changes

- `/api/generate_course` 改为调用 `CourseService.generate_course`，让真实入口使用课程蓝图 prompt。
- 课程生成返回的节点必须携带蓝图契约字段：学习目标、前置依赖、误区、验收标准、范围边界。
- 手动生成子节点接口改为调用 `CourseService.generate_sub_nodes`，与后台自动生成使用同一服务。
- 保留旧 API 响应字段兼容：`course_id`、`course_name`、`nodes`、`difficulty`、`style`、`requirements`。
- 不删除旧 `ai_service`，只停止课程生成主入口依赖旧大纲链路。

## Impact

- 影响 `backend/routers/courses.py`、`backend/routers/nodes.py`、`backend/course_service.py`。
- 新增或调整最小测试，覆盖 `/api/generate_course` 的统一入口、蓝图字段贯通和手动子节点接口。
- 不改变前端请求路径，前端仍调用现有 `/api/generate_course` 和 `/api/courses/{course_id}/auto_generate`。
