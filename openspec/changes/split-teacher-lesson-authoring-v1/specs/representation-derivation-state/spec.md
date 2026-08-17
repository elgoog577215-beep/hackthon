## ADDED Requirements

### Requirement: 表达来源支持教师讲次教案作用域
系统 MUST 支持以教师讲次教案修订和讲次知识快照构建 `slide_deck` 来源合同，并将作用域限制在一个 `LessonUnit`。现有学生 CourseDocument 来源合同保持兼容。

#### Scenario: 构建第二讲主课件
- **WHEN** 教师选择基于第二讲教案修订生成主课件
- **THEN** 来源合同只包含第二讲小节、教案模块和知识依据
- **AND** 生成结果登记在第二讲 PPT 资产下

#### Scenario: 学生构建原课程PPT
- **WHEN** 学生端或原课程工作台使用现有 CourseDocument 构建PPT
- **THEN** 系统继续使用原来源合同与接口语义
- **AND** 不要求教师讲次资产存在
