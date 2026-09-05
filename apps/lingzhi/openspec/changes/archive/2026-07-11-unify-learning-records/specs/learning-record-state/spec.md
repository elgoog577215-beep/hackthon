# 学习记录状态规格

## ADDED Requirements

### Requirement: 四类记录必须拥有明确边界

系统 MUST 只用 note、issue、review_task 和 bookmark 表达用户主动保留的学习记录，正式错题与作答 MUST NOT 复制为新的记录真源。

#### Scenario: 学生答错正式题目

- **WHEN** 正式练习产生错误作答
- **THEN** 系统 MUST 保存作答事实
- **AND** 系统 MUST NOT 自动创建笔记或未解决问题

### Requirement: 记录必须绑定版本化语义位置

每条记录 MUST 保存课程版本、节点、目标修订和可用的内容块修订；课程更新后 MUST 解析锚点并返回迁移状态，不得删除历史记录或随机跳转。

#### Scenario: 原内容块已经更新

- **WHEN** 用户打开绑定旧内容块修订的记录
- **THEN** 系统 MUST 返回当前可映射位置
- **AND** 系统 MUST 标明内容已经变化

### Requirement: 问题和复习任务必须具有生命周期

issue 与 review_task 的状态变化 MUST 被校验并追加事实事件；note 与 bookmark 的归档 MUST 保留历史而不是物理删除。

#### Scenario: 未解决问题被验证解决

- **WHEN** 用户把 awaiting_verification 问题标记为 resolved
- **THEN** 当前记录 MUST 更新状态与修订号
- **AND** 系统 MUST 追加 learning_record_status_changed 事件

### Requirement: AI 回答不得自动成为笔记

AI 会话默认 MUST 保持临时，只有用户明确执行保存动作后才能创建 note。

#### Scenario: AI 完成一次正文解释

- **WHEN** AI 返回回答与引用
- **THEN** 系统 MUST NOT 自动写入学习记录
- **AND** 用户点击保存后系统 MUST 创建一条来源为 assistant_saved 的 note

### Requirement: 旧注释迁移必须幂等且降级

旧 annotation MUST 按来源映射到新记录，迁移 MUST 幂等；旧错题注释最多成为低置信 review_task，不得证明当前掌握状态。

#### Scenario: 同一课程重复执行迁移

- **WHEN** 客户端再次提交旧注释迁移
- **THEN** 系统 MUST 返回零条重复创建
- **AND** 已迁移记录和事件 MUST 保持不变
