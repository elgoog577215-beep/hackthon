## MODIFIED Requirements

### Requirement: 课程内容操作必须使用统一课程服务

节点重写、节点扩展、节点摘要和课程内定位 MUST 通过 `CourseService` 执行。旧 `AICourseService` 和 `AICourseServiceV5` MUST NOT 作为后端可调用服务保留；课程 AI 能力的生产入口只允许落在 `CourseService`。

#### Scenario: 用户重写整个节点

- **WHEN** 客户端调用 `/api/courses/{course_id}/nodes/{node_id}/redefine`
- **THEN** 服务端 MUST 使用 `CourseService` 构造课程上下文、节点契约和用户要求
- **AND** 返回值 MUST 保持兼容，包含 `node_content`
- **AND** 节点的 `content_blocks` MUST 与最终 `node_content` 同步

#### Scenario: 用户扩展节点内容

- **WHEN** 客户端调用 `/api/courses/{course_id}/nodes/{node_id}/extend`
- **THEN** 服务端 MUST 使用 `CourseService` 生成与课程上下文一致的补充内容
- **AND** 响应 MUST 保持现有 `content` 字段

#### Scenario: 后端初始化 AI 门面

- **WHEN** `ai_service` 模块被导入
- **THEN** `AIService` MUST NOT 继承或导入旧课程生成服务
- **AND** quiz、QA、graph、learning、diagram、profile 能力 MUST 保持可用
