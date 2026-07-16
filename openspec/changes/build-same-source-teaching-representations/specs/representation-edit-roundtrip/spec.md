## ADDED Requirements

### Requirement: 表示编辑必须区分表现变化与语义变化

系统 MUST 将表示编辑分类为表现、等义、语义或无法判断。表现和已验证等义修改 MAY 只更新表示修订；语义修改 MUST 转换为统一课程变化候选；无法判断的修改 MUST 等待用户决定。

#### Scenario: 修改 PPT 页面颜色

- **WHEN** 用户只修改主题颜色和布局
- **THEN** 系统 MUST 只更新表示修订
- **AND** MUST NOT 修改课程正文、知识或题目

#### Scenario: 修改 PPT 中的数学结论

- **WHEN** 用户将例子改成具有不同数学含义的新结论
- **THEN** 系统 MUST 生成课程语义变化候选并展示影响范围
- **AND** 用户确认前 MUST NOT 覆盖正式课程

#### Scenario: 系统无法判断标题修改是否等义

- **WHEN** 编辑分类结果为无法判断
- **THEN** 系统 MUST 让用户选择只改当前表示或改变课程含义
- **AND** MUST NOT 静默选择任一路径
