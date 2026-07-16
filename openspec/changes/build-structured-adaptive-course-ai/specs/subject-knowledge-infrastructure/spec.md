## ADDED Requirements

### Requirement: 当前课程知识库必须拥有唯一产品知识身份

系统 MUST 将与 `course_id` 一一对应的 `CourseKnowledgeBase` 作为当前课程唯一的产品知识库和运行时知识坐标。课程正文、课件、题目、AI、学习证据和个人状态 MUST 引用当前课程知识 ID，MUST NOT 以跨课程知识 ID 取代当前课程身份。

#### Scenario: 新课程没有任何外部学科参考

- **WHEN** 系统生成一门无法匹配任何外部学科目录的新课程
- **THEN** 系统 MUST 仍能生成、审查和发布完整 `CourseKnowledgeBase`
- **AND** 正文、题目、AI 和个人状态 MUST 能正常引用当前课程知识 ID

### Requirement: 跨课程知识设施只能作为可选参考

现有 `SubjectKnowledgeLibrary` MAY 提供规范术语、别名、覆盖检查或生成校准候选，但 MUST NOT 成为当前课程知识生成、发布、读取、AI 使用或掌握投影的必选前置。参考匹配 MUST NOT 创建或替换当前课程知识身份。

#### Scenario: 参考目录存在精确术语

- **WHEN** 一个课程知识候选与参考目录中的术语或别名匹配
- **THEN** 系统 MAY 保存可追溯的参考建议
- **AND** 当前课程知识点 MUST 保留自己的 `course_id`、`knowledge_id`、颗粒度和掌握标准

#### Scenario: 参考目录缺失或冲突

- **WHEN** 外部参考缺失、版本落后、只有部分覆盖或与当前课程边界冲突
- **THEN** 系统 MUST 以当前课程目标、资料和知识质量门完成审查
- **AND** MUST NOT 清空、降级、重编号或阻断当前课程知识库

### Requirement: 个人课程变化不得反向写入跨课程参考

当前课程中的知识新增、细化、关系、能力、易错、掌握标准和绑定变化 MUST 只作用于当前 `CourseKnowledgeBase`。任何跨课程参考目录更新 MUST 属于未来独立的教师或治理工作流，MUST NOT 由本变更自动执行。

#### Scenario: 当前课程形成高质量新知识点

- **WHEN** 一个当前课程知识候选通过质量门并被用户接受
- **THEN** 它 MAY 成为当前课程活动知识点
- **AND** 其他课程 MUST NOT 自动读取该知识点
- **AND** 系统 MUST NOT 自动创建或修改跨课程参考条目
