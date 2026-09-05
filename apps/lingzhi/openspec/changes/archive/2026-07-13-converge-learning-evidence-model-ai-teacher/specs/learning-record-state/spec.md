## ADDED Requirements

### Requirement: 旧 annotation 不得继续作为正式记录写入口

新笔记、问题、复习任务和书签 MUST 通过 LearningRecord 领域命令创建。旧 annotation 只允许幂等迁移或只读历史访问，不得为新用户动作继续保存第二份记录或以共享默认身份追加事件。

#### Scenario: 当前学习页保存一条笔记

- **WHEN** 用户从正文或 AI 老师明确保存笔记
- **THEN** 系统 MUST 创建或更新 LearningRecord 并追加关联事件
- **AND** MUST NOT 同时写入 annotation 存储
