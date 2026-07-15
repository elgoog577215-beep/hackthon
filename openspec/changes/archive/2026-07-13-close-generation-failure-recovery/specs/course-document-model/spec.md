## ADDED Requirements

### Requirement: 块候选必须在模型调用前持久化并可恢复

系统 MUST 在调用模型前创建状态为 `generating` 的块候选，保存目标修订、原块载荷、用户要求和生成所有者。模型异常或服务中断 MUST 留下可查询的失败候选，正式课程文档 MUST 保持不变。

#### Scenario: 同一候选请求并发到达

- **WHEN** 多个请求使用相同 `course_id`、`block_id` 和 `request_id` 创建候选
- **THEN** 只有一个请求 MUST 获得模型生成权
- **AND** 其他请求 MUST 返回同一个候选状态
- **AND** 系统 MUST NOT 重复调用模型

#### Scenario: 模型调用失败

- **WHEN** 块候选生成期间模型返回异常
- **THEN** 候选 MUST 标记为 `generation_failed` 并保存失败原因
- **AND** 目标课程与目标块修订 MUST 保持不变
- **AND** 用户 MUST 能对同一候选执行显式重试

#### Scenario: 服务重启后读取生成中候选

- **WHEN** 候选仍标记为 `generating`，但生成所有者属于已结束的服务进程
- **THEN** 系统 MUST 将其修正为可恢复的中断失败
- **AND** MUST NOT 假装原模型调用仍在运行

### Requirement: 学习现场必须能找回目标块的最近候选

规范课程的右侧 AI 老师 MUST 能按当前课程修订和块修订读取最近候选，并恢复生成中、生成失败、质量失败、待应用或已应用状态；不得要求用户进入独立页面寻找失败任务。

#### Scenario: 浏览器刷新后重新打开目标块

- **WHEN** 用户刷新页面并再次打开同一规范课程块的正式改进入口
- **THEN** 前端 MUST 读取该块当前修订上的最近候选
- **AND** MUST 恢复候选预览、失败原因或生成状态
- **AND** MUST NOT 因刷新创建第二个候选

#### Scenario: 候选目标修订已经变化

- **WHEN** 最近候选的课程修订或块修订不再匹配当前课程
- **THEN** 系统 MUST 将候选视为过期
- **AND** 前端 MUST 要求基于当前内容重新生成
- **AND** 过期候选 MUST NOT 被重试或应用
