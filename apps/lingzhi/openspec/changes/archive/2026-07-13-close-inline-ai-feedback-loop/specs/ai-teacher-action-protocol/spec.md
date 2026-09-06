## ADDED Requirements

### Requirement: 块级 AI 回答必须支持显式效果反馈

完整的块级 AI 回答 MUST 提供“已解决”和“还不清楚”两项显式反馈，并将选择写入统一 `LearningEvent`。反馈 MUST 关联当前用户、课程、节点、会话、assistant 消息、块级动作和稳定内容锚点；同一消息的重复提交 MUST 幂等。一次反馈 MUST NOT 自动创建学习记录、正式题目、诊断、补救、掌握结论、课程改写或唯一下一步。

#### Scenario: 用户确认回答已解决问题

- **WHEN** 用户对一条已完成的块级 AI 回答选择“已解决”
- **THEN** 系统 MUST 记录一条 `assistant_answer_feedback_submitted` 学习事件
- **AND** 结果 MUST 标记为 `resolved` 并保留会话、消息与内容块引用
- **AND** 系统 MUST NOT 自动执行其他 AI 或领域动作

#### Scenario: 用户仍然不清楚

- **WHEN** 用户选择“还不清楚”
- **THEN** 系统 MUST 记录结果为 `unclear` 的回答反馈事件
- **AND** 当前回答 MUST 继续保留并允许用户自行选择继续追问
- **AND** 系统 MUST NOT 自动生成下一步、题目或补救任务

#### Scenario: 回答尚未完成或不属于当前用户

- **WHEN** 客户端对生成中、失败、不存在或不属于当前用户的 assistant 消息提交反馈
- **THEN** 后端 MUST 拒绝写入学习事件
- **AND** MUST NOT 仅凭客户端提供的消息 ID 创建事实
