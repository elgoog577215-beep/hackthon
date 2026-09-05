## ADDED Requirements

### Requirement: 原始对话证据不得直接写入稳定学习者模型

系统 MAY 登记当前课程中的每条用户文字为 `EvidenceItem`，但 MUST NOT 因登记而直接修改 `LearnerModel`。基于对话形成的教学适应假设 MUST 保持独立、有来源、可反证，并且只能通过正式领域事实影响下一次确定性模型重算。

#### Scenario: 用户明确要求当前章节讲细一点

- **WHEN** 系统记录该用户输入并生成局部课程候选
- **THEN** `LearnerModel` MUST NOT 自动产生全局难度偏好或稳定能力结论
- **AND** 适应假设 MUST 保留当前章节范围

### Requirement: 课程适应判断与正式掌握投影必须分离

候选课程内容、候选中的非正式理解检查、用户接受修改和 AI 对修改效果的判断 MUST NOT 自动成为正式掌握证据。只有既有正式领域规则认可的作答、诊断、复验和记录事实才能改变相关正式投影。

#### Scenario: 用户接受更详细解释

- **WHEN** 用户接受课程补写候选
- **THEN** 系统 MAY 记录修改决定与后续效果基线
- **AND** MUST NOT 将用户标记为已经掌握或稳定薄弱
