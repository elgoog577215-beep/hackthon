## ADDED Requirements

### Requirement: 当前课程知识库必须拥有唯一产品知识身份

系统 MUST 将与 `course_id` 一一对应的 `CourseKnowledgeBase` 作为当前课程唯一的产品知识库和运行时知识坐标。课程正文、课件、题目、AI、学习证据和个人状态 MUST 引用当前课程知识 ID，MUST NOT 以跨课程知识 ID 取代当前课程身份。

#### Scenario: 新课程没有任何外部学科参考

- **WHEN** 系统生成一门无法匹配任何外部学科目录的新课程
- **THEN** 系统 MUST 仍能生成、审查和发布完整 `CourseKnowledgeBase`
- **AND** 正文、题目、AI 和个人状态 MUST 能正常引用当前课程知识 ID

### Requirement: 新链不得读取或维护跨课程知识设施

新课程生成、课程知识维护、AI 使用、练习分析、证据索引和掌握投影 MUST
只读取请求中 `course_id` 对应的 `CourseKnowledgeBase`。现有
`SubjectKnowledgeLibrary` MUST NOT 作为术语参考、生成校准、覆盖检查或关系来源
进入新链；它只 MAY 在显式历史迁移中被读取，并且迁移结果 MUST 创建当前课程内
的新身份。

#### Scenario: 其他课程存在同名知识

- **WHEN** 当前课程生成或维护一个与其他课程同名的知识点
- **THEN** 系统 MUST 只依据当前课程目标、资料和质量门决定其边界
- **AND** MUST NOT 查询、复用或修改其他课程的知识 ID、关系或掌握标准

#### Scenario: 迁移旧跨课程知识

- **WHEN** 维护者显式启动历史知识迁移
- **THEN** 系统 MAY 读取旧 `SubjectKnowledgeLibrary` 条目作为迁移输入
- **AND** MUST 为目标课程创建新的 `course_id` 范围内身份和来源记录
- **AND** 新运行链 MUST NOT 保留对旧条目的运行时依赖

### Requirement: 课程知识维护必须具有独立当前课程维护面

知识新增、细化、拆分、合并、关系、能力、易错、掌握标准和绑定变化 MUST
进入课程知识维护面，显示影响并由有权限的维护者确认。该维护面 MUST 固定一个
`course_id`，MUST NOT 提供跨课程发布、同步或扩散操作。

#### Scenario: 当前课程形成高质量新知识点

- **WHEN** 一个当前课程知识候选通过质量门并被课程维护者接受
- **THEN** 它 MUST 只成为当前课程活动知识点
- **AND** 其他课程 MUST 保持不变
