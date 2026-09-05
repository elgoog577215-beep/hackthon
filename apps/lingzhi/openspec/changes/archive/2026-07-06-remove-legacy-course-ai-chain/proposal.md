## Why

课程生成、节点重写、扩展、摘要和定位已经迁移到 `CourseService`。旧 `AICourseService` 和未接入生产入口的 `AICourseServiceV5` 继续留在后端，会让后续维护者误判真实链路，也可能让新功能重新接回旧 prompt。

## What Changes

- 从 `AIService` 门面移除旧课程服务继承。
- 删除旧课程生成服务文件 `backend/ai_course_service.py` 和 `backend/ai_course_service_v5.py`。
- 保留 quiz、QA、graph、learning、diagram、profile 等非课程 AI 服务的现有门面。
- 更新规格，明确旧课程 AI 服务不再作为 legacy 备份保留。
