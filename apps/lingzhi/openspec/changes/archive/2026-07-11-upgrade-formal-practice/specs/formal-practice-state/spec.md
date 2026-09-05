## ADDED Requirements

### Requirement: 每次正式作答必须拥有独立 Attempt

系统 MUST 为用户针对正式题目修订的一次作答创建稳定 PracticeAttempt；提交后的答案 MUST 不可覆盖，重新练习 MUST 创建新的 Attempt。

#### Scenario: 学生提交后重新练习同一道题

- **WHEN** 已评分 Attempt 的学生选择重新练习
- **THEN** 系统 MUST 创建新的 attempt_id
- **AND** 原答案、提示和评分 MUST 保持不变

### Requirement: 活动草稿必须可恢复且不得静默冲突

活动 Attempt MUST 使用服务端修订号保存草稿，并允许本地缓存提供断网保护；跨设备冲突 MUST 被保留或显式返回，不得使用最后写入静默覆盖。

#### Scenario: 两个设备修改同一草稿

- **WHEN** 旧修订设备提交草稿更新
- **THEN** 系统 MUST 返回冲突
- **AND** 当前服务端草稿 MUST 保持不变

### Requirement: 提示与 AI 帮助必须影响证据强度

系统 MUST 不可变地记录已经揭示的提示等级、完整解析和正式练习中的 AI 支持，并据此计算证据强度。

#### Scenario: 学生使用三级提示后答对

- **WHEN** Attempt 已揭示三级提示并达到题目通过线
- **THEN** 结果 MUST 标记为 scaffolded
- **AND** 本次结果 MUST NOT 单独把目标投影为 mastered

### Requirement: 开放题不得伪造精确自动评分

开放题评分 MUST 返回量规分项、方法和置信度；无法可靠判断时 MUST 进入待评阅，不得使用关键词命中冒充可靠评分。

#### Scenario: AI 评分置信度不足

- **WHEN** 评分器无法可靠区分通过与未通过
- **THEN** Attempt MUST 进入 grading 或 pending_review 结果
- **AND** 掌握投影 MUST 视为证据不足

### Requirement: 当前掌握只使用当前版本有效证据

掌握投影 MUST 只使用与当前目标、题目和掌握标准修订兼容的有效 Attempt；历史失败、纠正和旧版本证据 MUST 保留但不得被最后一次答案覆盖。

#### Scenario: 课程更新了题目与掌握标准

- **WHEN** 旧 Attempt 无法映射到新修订
- **THEN** 当前掌握 MUST 不再使用该 Attempt
- **AND** 历史页面 MUST 继续展示旧版本证据

### Requirement: 旧测验数据必须降级迁移并退出生产

旧浏览器错题、测验历史和旧后端记录 MUST 幂等导入为低置信历史，MUST NOT 创建正式掌握证据；迁移完成后生产界面与写入链路 MUST 不再依赖旧数据源。

#### Scenario: 同一旧错题重复迁移

- **WHEN** 客户端重复提交相同迁移键
- **THEN** 系统 MUST 不重复创建历史事件
- **AND** 当前目标掌握 MUST 保持不变
