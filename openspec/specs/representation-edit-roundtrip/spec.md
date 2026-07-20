# representation-edit-roundtrip Specification

## Purpose
TBD - created by archiving change build-same-source-teaching-representations. Update Purpose after archive.
## Requirements
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

### Requirement: 表现修改必须在兼容重建后保留

系统 MUST 将仅属于演示文稿表现层的修改与其基础值一同保存。课程重建后，兼容修改 MUST 重放；页面被删除或基础语义字段变化时，系统 MUST 记录冲突，不得静默覆盖新课程语义。

#### Scenario: 修改页面版式后课程其他小节更新

- **WHEN** 目标页面仍存在且基础内容兼容
- **THEN** 新课件 MUST 保留该页面版式修改

#### Scenario: 修改页面标题后基础标题发生语义变化

- **WHEN** 新课程生成出的基础标题不再等于表现修改的基础值
- **THEN** 系统 MUST 保留新基础标题
- **AND** MUST 记录表现修改冲突供维护者处理
