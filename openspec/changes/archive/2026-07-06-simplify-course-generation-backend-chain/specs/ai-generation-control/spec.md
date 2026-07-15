## ADDED Requirements

### Requirement: 课程生成入口必须使用统一课程服务

课程生成主入口 MUST 调用 `CourseService` 生成课程蓝图，不能再使用旧 `AIService/AICourseService` 生成课程大纲。

#### Scenario: 用户创建新课程

- **WHEN** 客户端调用 `/api/generate_course`
- **THEN** 服务端 MUST 使用 `CourseService.generate_course` 生成课程
- **AND** 响应 MUST 包含 `course_id`、`course_name` 和 `nodes`
- **AND** 课程 MUST 保存到存储层，供后续 `/auto_generate` 使用

### Requirement: 课程节点必须携带蓝图契约字段

课程生成返回的 L2 节点 MUST 携带后续正文生成所需的蓝图契约字段。

#### Scenario: 课程蓝图包含小节契约

- **WHEN** `/api/generate_course` 返回 L2 节点
- **THEN** 每个 L2 节点 SHOULD 包含 `learning_objective`
- **AND** SHOULD 包含 `prerequisite_node_ids`
- **AND** SHOULD 包含 `misconceptions`
- **AND** SHOULD 包含 `assessment`
- **AND** SHOULD 包含 `scope_boundary`

### Requirement: 子节点生成接口必须与后台生成使用同一课程服务

手动子节点生成接口 MUST 使用 `CourseService.generate_sub_nodes`，与后台自动生成链路保持一致。

#### Scenario: 用户手动补充子节点

- **WHEN** 客户端调用 `/api/courses/{course_id}/nodes/{node_id}/subnodes`
- **THEN** 服务端 MUST 使用 `CourseService.generate_sub_nodes`
- **AND** 已有子节点时 MUST 直接返回已有子节点，不重复生成
