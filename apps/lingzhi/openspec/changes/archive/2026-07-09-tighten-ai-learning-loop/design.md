## Context

灵知的产品闭环是：

```text
课程内容 -> 学习行为 -> 学习痕迹 -> 用户画像/学习状态 -> AI 老师 -> 课程迭代
```

当前代码已经具备这些局部能力，但边界还不够紧。最小改造策略是复用已有主干，让数据顺着同一条链路流动。

## Data Flow

```text
前端问答
-> POST /api/ask_events
-> record_learning_event(user_id)
-> AIQAService.answer_question_events
-> build_ai_learning_context(user_id, course_id, node_id)
-> SSE: answer / final_answer / metadata
-> assistant_answer_completed 学习事件

课程生成
-> /api/course-generation/generate
-> CourseService.generate_course
-> GenerationQualityReport
-> TaskManager auto_generate
-> CourseService.generate_node_content_stream
-> ai_output_quality_assessed 学习事件
-> 后续课程质量报告读取质量事件
```

## Boundaries

- `LearningEvent` 记录发生过什么，是学习痕迹事实底座。
- `LearnerState` 归纳当前状态，区分事实和推断。
- `TeachingDecision` 只表达教学意图，不覆盖课程事实。
- `build_ai_learning_context` 负责编排课程上下文、学习者上下文、学习者状态和教学决策。
- `GenerationQualityReport` 只标记质量和修复建议，不自动重写课程。

## User Identity

本阶段只接受 `X-User-Id` 作为原型阶段用户标识。为空时回退 `DEFAULT_USER_ID`。它不承担鉴权职责，只用于隔离本地学习事件和上下文。

## Compatibility

- `/api/ask` 保留文本流和 `---METADATA---` 兼容协议。
- `/api/ask_events` 是前端默认问答协议。
- `/api/course-generation/generate` 仍是唯一课程生成入口。
- `TaskManager` WebSocket payload 不变。

## Non-Goals

- 不实现登录、权限、用户表或复杂 session。
- 不做 LLM 评审平台。
- 不新增向量库、Agent 框架或平行课程生成服务。
- 不自动根据质量事件重写课程；只给出可执行修复建议。
