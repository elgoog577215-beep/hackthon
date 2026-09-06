## ADDED Requirements

### Requirement: 版本变化必须提供可执行迁移计划

系统 MUST 根据当前课程版本、旧快照、活动 Attempt、诊断工作流和学习记录投影唯一版本迁移计划；计划 MUST 区分可安全重映射、需显式确认、必须失效和仅保留历史的对象。

#### Scenario: 旧学习现场遇到新课程版本

- **WHEN** LearningSnapshot 或活动任务的课程版本不是当前版本
- **THEN** LearningContinuation MUST 返回 confirm_version_change 主动作
- **AND** 迁移计划 MUST 说明目标版本、锚点解析状态和受影响对象
- **AND** 前端 MUST NOT 仅通过切换版本页面解除阻断

### Requirement: 版本确认必须校验运行时修订并保持幂等

版本确认命令 MUST 校验客户端读取的连续性投影修订；修订过期时 MUST 拒绝写入并返回当前投影。重复确认同一版本变化 MUST NOT 重复失效对象或追加重复事实。

#### Scenario: 用户确认处理版本变化

- **WHEN** 用户提交当前 projection revision 和幂等请求 ID
- **THEN** 服务端 MUST 串行迁移当前学习现场并失效旧活动任务
- **AND** 旧 Attempt、诊断和记录的历史课程版本 MUST 保持不变
- **AND** 完成后运行时 MUST 不再被同一批版本冲突阻断

### Requirement: 无法安全映射的现场不得随机迁移

阅读锚点只有在 exact、updated_block、fingerprint_remap 或用户明确接受 node_fallback 时才能更新到当前版本；course_fallback 和 unavailable MUST 要求显式目标节点。

#### Scenario: 原内容在新版本中已删除

- **WHEN** 旧锚点只能回退到课程任意位置或完全不可解析
- **THEN** 确认命令 MUST 返回需要目标节点的错误
- **AND** 旧快照 MUST 保持原版本和原位置

### Requirement: 旧正式证据不得证明新修订

课程版本变化后，当前掌握投影 MUST 只接受当前目标修订、题目修订和掌握标准修订对应的正式证据；旧版本对象 MUST 作为历史证据保留但不得自动换算。

#### Scenario: cv2 更新正式题目和掌握标准

- **WHEN** cv1 的 graded Attempt 对应题目或标准修订不属于 cv2
- **THEN** cv2 当前掌握状态 MUST NOT 使用该 Attempt
- **AND** 学习进度 MAY 显示存在历史证据但不得显示为新版本已掌握
