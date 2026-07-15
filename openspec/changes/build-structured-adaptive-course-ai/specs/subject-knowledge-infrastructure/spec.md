## ADDED Requirements

### Requirement: 系统必须在正式学科库与课程映射之间提供课程知识层

系统 MUST 使用 `CourseKnowledgeBase` 表达随当前课程生成并可继续细化的课程语义结构。该层 MUST 使用课程局部稳定 ID，并 MUST 通过 `CourseKnowledgeMap` 连接正式学科知识、课程块、目标和学习资产；MUST NOT 取代跨课程正式 `SubjectKnowledgeLibrary`。

#### Scenario: 正式学科包只覆盖部分课程

- **WHEN** 新课程包含正式学科包尚未覆盖的合法内容
- **THEN** `CourseKnowledgeBase` MUST 保留课程局部节点
- **AND** `CourseKnowledgeMap` MUST 标记未映射或部分映射状态
- **AND** 学习主链 MUST 能继续使用当前课程知识层

### Requirement: 学生课程 AI 不得自动升级正式学科知识

个人课程中的知识新增、细化、关系与映射变化 MUST 只作用于当前课程知识库。任何升级到跨课程正式知识库的动作 MUST 进入未来教师或治理工作流，MUST NOT 由本变更自动执行。

#### Scenario: 个人课程形成高质量新知识节点

- **WHEN** 一个课程局部节点通过当前课程质量门并被用户接受
- **THEN** 它 MAY 在当前课程中成为活动节点
- **AND** MUST NOT 自动出现在其他课程或正式学科包
